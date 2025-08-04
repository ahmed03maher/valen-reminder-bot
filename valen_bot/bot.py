"""
Main Telegram bot implementation for Valen journaling reminders.

This script defines handlers and scheduled jobs for managing user
subscriptions, sending daily reminder messages, tracking interactions,
and re-engaging inactive users. It uses python-telegram-bot v20's
asyncio-based API and a SQLite backend via the db.py module.

Environment variables expected:

* BOT_TOKEN: Telegram bot token from BotFather.
* ADMIN_ID: (optional) Telegram user ID of the admin to receive
  inactivity alerts.

Before running locally, install dependencies from requirements.txt and
create a `.env` file at project root with the required variables. For
deployment on platforms like Railway, configure these variables in the
service settings.
"""

import os
import re
import asyncio
import logging
from typing import Dict, List
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackContext,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from db import Database, set_user_time, get_user_times


# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


class ValenBot:
    """Encapsulates bot behavior and state."""

    def __init__(self, token: str, admin_id: str | None = None) -> None:
        self.db = Database()
        self.admin_id = int(admin_id) if admin_id and isinstance(admin_id, str) and admin_id.isdigit() else None
        self.timezone = ZoneInfo("Africa/Cairo")
        self.application: Application = ApplicationBuilder().token(token).build()
        self.user_jobs: Dict[int, List] = {}

        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("stop", self.stop))
        self.application.add_handler(CommandHandler("setmorning", set_morning))
        self.application.add_handler(CommandHandler("setevening", set_evening))
        self.application.add_handler(
            MessageHandler(filters.ALL & (~filters.COMMAND), self.handle_message)
        )

        # Inactivity check
        self.application.job_queue.run_daily(
            self.check_inactivity,
            time=time(hour=9, minute=0, tzinfo=self.timezone),
            name="inactivity_checker",
        )

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        self.db.add_user(user_id)
        await self.cancel_user_jobs(user_id)
        await self.schedule_user_reminders(user_id)
        await update.message.reply_text(
            "Welcome to Valen! I'll remind you to write in your journal each day at 10 AM and 10 PM.",
            quote=False,
        )

    async def stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        self.db.remove_user(user_id)
        await self.cancel_user_jobs(user_id)
        await update.message.reply_text(
            "You've been unsubscribed from Valen reminders. Send /start to re-enable.",
            quote=False,
        )

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        user_record = self.db.get_user(user_id)
        if not user_record or user_record[-1] == 0:
            return
        self.db.update_interaction(user_id)
        logger.info(f"Recorded interaction for user {user_id}")

    async def send_reminder(self, context: CallbackContext) -> None:
        user_id: int = context.job.data["user_id"]
        message = (
            "Don't forget to log your thoughts in Valen today! "
            "You can reply to this message with your check‑in or an emoji."
        )
        try:
            await context.bot.send_message(chat_id=user_id, text=message)
        except Exception as exc:
            logger.warning(f"Failed to send reminder to {user_id}: {exc}")
            await self.cancel_user_jobs(user_id)
            self.db.remove_user(user_id)

    async def schedule_user_reminders(self, user_id: int) -> None:
        await self.cancel_user_jobs(user_id)
        record = self.db.get_user(user_id)
        if record is None:
            return
        _, hour1, hour2, _, subscribed = record
        if subscribed == 0:
            return
        job1 = self.application.job_queue.run_daily(
            self.send_reminder,
            time=time(hour=hour1, minute=0, tzinfo=self.timezone),
            data={"user_id": user_id},
            name=f"reminder1_{user_id}",
        )
        job2 = self.application.job_queue.run_daily(
            self.send_reminder,
            time=time(hour=hour2, minute=0, tzinfo=self.timezone),
            data={"user_id": user_id},
            name=f"reminder2_{user_id}",
        )
        self.user_jobs[user_id] = [job1, job2]
        logger.info(f"Scheduled reminders for user {user_id} at {hour1}:00 and {hour2}:00")

    async def cancel_user_jobs(self, user_id: int) -> None:
        jobs = self.user_jobs.pop(user_id, [])
        for job in jobs:
            try:
                job.schedule_removal()
                logger.info(f"Cancelled job {job.name}")
            except Exception:
                pass

    async def check_inactivity(self, context: CallbackContext) -> None:
        today = date.today()
        for user_id, _, _, last_date_str in self.db.get_active_users():
            try:
                last_date = date.fromisoformat(last_date_str) if last_date_str else today - timedelta(days=4)
            except ValueError:
                self.db.update_interaction(user_id, today)
                continue

            if (today - last_date).days >= 3:
                message = (
                    "Hey, haven’t seen your check‑ins lately. Everything okay? "
                    "Remember, journaling helps reflect and grow."
                )
                try:
                    await context.bot.send_message(chat_id=user_id, text=message)
                except Exception as exc:
                    logger.warning(f"Failed to send re-engagement message to {user_id}: {exc}")
                if self.admin_id:
                    try:
                        await context.bot.send_message(
                            chat_id=self.admin_id,
                            text=f"User {user_id} has been inactive for {(today - last_date).days} days.",
                        )
                    except Exception as exc:
                        logger.warning(f"Failed to alert admin for user {user_id}: {exc}")

    async def run(self) -> None:
        for user_id, _, _, _ in self.db.get_active_users():
            await self.schedule_user_reminders(user_id)
        logger.info("Bot started and ready.")
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        await self.application.updater.idle()


# --- COMMAND HANDLERS ---

async def set_morning(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Please send a time. Example: /setmorning 8:30 AM")
        return
    time_input = " ".join(context.args)
    parsed = parse_time_string(time_input)
    if parsed:
        set_user_time(user_id, "morning", parsed)
        await update.message.reply_text(f"Morning reminder set to {parsed}")
        await context.application.bot_data["valen_bot"].schedule_user_reminders(user_id)
    else:
        await update.message.reply_text("❌ Couldn’t understand the time format. Try '8:30 AM' or '20:15'.")

async def set_evening(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Please send a time. Example: /setevening 9 PM")
        return
    time_input = " ".join(context.args)
    parsed = parse_time_string(time_input)
    if parsed:
        set_user_time(user_id, "evening", parsed)
        await update.message.reply_text(f"Evening reminder set to {parsed}")
        await context.application.bot_data["valen_bot"].schedule_user_reminders(user_id)
    else:
        await update.message.reply_text("❌ Couldn’t understand the time format. Try '9 PM' or '21:00'.")


# --- TIME PARSING ---

def parse_time_string(time_str):
    import dateutil.parser
    try:
        t = dateutil.parser.parse(time_str).time()
        return f"{t.hour:02d}:{t.minute:02d}"
    except Exception:
        return None


# --- ENTRY POINT ---

def main() -> None:
    load_dotenv()
    token = os.environ.get("BOT_TOKEN")
    admin_id = os.environ.get("ADMIN_ID")

    if not token:
        raise RuntimeError("BOT_TOKEN is not set. Define it in a .env file or environment variables.")

    bot = ValenBot(token=token, admin_id=admin_id)
    bot.application.bot_data["valen_bot"] = bot

    try:
        asyncio.run(bot.run())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")


if __name__ == "__main__":
    main()
