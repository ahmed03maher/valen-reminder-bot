"""
Main Telegram bot implementation for Valen journaling reminders.

This script defines handlers and scheduled jobs for managing user
subscriptions, sending daily reminder messages, tracking interactions,
and re-engaging inactive users. It uses python-telegram-bot v20's
asyncio-based API and a SQLite backend via the db.py module.

Environment variables expected (see `.env.example`):

* BOT_TOKEN: Telegram bot token from BotFather.
* ADMIN_ID: (optional) Telegram user ID of the admin to receive
  inactivity alerts.

Before running locally, install dependencies from requirements.txt and
create a `.env` file at project root with the required variables. For
deployment on platforms like Render or Railway, configure these
variables in the service settings.
"""

import asyncio
import logging
import os
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from typing import Dict, List

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

from .db import Database


# Configure logging to stdout for easier debugging.
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


class ValenBot:
    """Encapsulates bot state and behaviour for easier testing."""

    def __init__(self, token: str, admin_id: str | None = None) -> None:
        self.db = Database()
        self.admin_id = int(admin_id) if admin_id and admin_id.isdigit() else None
        self.timezone = ZoneInfo("Africa/Cairo")
        self.application: Application = ApplicationBuilder().token(token).build()

        # Map user IDs to lists of scheduled job instances
        self.user_jobs: Dict[int, List] = {}

        # Register handlers
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("stop", self.stop))
        # Catch all text/emoji messages to detect replies or reactions
        self.application.add_handler(
            MessageHandler(filters.ALL & (~filters.COMMAND), self.handle_message)
        )

        # Schedule a daily inactivity check job at 09:00 Cairo time
        self.application.job_queue.run_daily(
            self.check_inactivity,
            time=time(hour=9, minute=0, tzinfo=self.timezone),
            name="inactivity_checker",
        )

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /start command: subscribe a user and schedule reminders."""
        user_id = update.effective_user.id
        # Add or reactivate user with default reminder times
        self.db.add_user(user_id)
        # Cancel any existing jobs for this user to avoid duplicates
        await self.cancel_user_jobs(user_id)
        # Schedule two daily reminders
        await self.schedule_user_reminders(user_id)
        # Send welcome message
        await update.message.reply_text(
            "Welcome to Valen! I'll remind you to write in your journal each day at 10 AM and 10 PM.",
            quote=False,
        )

    async def stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /stop command: unsubscribe a user and cancel reminders."""
        user_id = update.effective_user.id
        self.db.remove_user(user_id)
        await self.cancel_user_jobs(user_id)
        await update.message.reply_text(
            "You've been unsubscribed from Valen reminders. Send /start to re-enable.",
            quote=False,
        )

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Record user interactions when they reply or react to reminders."""
        user_id = update.effective_user.id
        # Ignore messages from unknown users who haven't started the bot
        user_record = self.db.get_user(user_id)
        if not user_record or user_record[-1] == 0:
            return

        # Determine if this is a reply to a bot message
        is_reply_to_bot = False
        if update.message and update.message.reply_to_message:
            is_reply_to_bot = update.message.reply_to_message.from_user.id == context.bot.id

        # For simplicity, count any message (reply, emoji, etc.) as an interaction
        if is_reply_to_bot or True:
            self.db.update_interaction(user_id)
            logger.info(f"Recorded interaction for user {user_id}")

    async def send_reminder(self, context: CallbackContext) -> None:
        """Send a reminder message to a specific user (scheduled job)."""
        job_data = context.job.data
        user_id: int = job_data["user_id"]
        # Compose reminder message
        message = (
            "Don't forget to log your thoughts in Valen today! "
            "You can reply to this message with your check‑in or an emoji."
        )
        try:
            await context.bot.send_message(chat_id=user_id, text=message)
        except Exception as exc:
            # If sending fails (e.g. blocked), log and unschedule jobs
            logger.warning(f"Failed to send reminder to {user_id}: {exc}")
            await self.cancel_user_jobs(user_id)
            self.db.remove_user(user_id)

    async def schedule_user_reminders(self, user_id: int) -> None:
        """Schedule daily reminder jobs for a user at their configured times."""
        # Ensure there are no duplicate jobs
        await self.cancel_user_jobs(user_id)
        record = self.db.get_user(user_id)
        if record is None:
            return
        _, hour1, hour2, _, subscribed = record
        if subscribed == 0:
            return
        # Create jobs
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
        """Cancel any scheduled reminder jobs for a user."""
        jobs = self.user_jobs.pop(user_id, [])
        for job in jobs:
            try:
                job.schedule_removal()
                logger.info(f"Cancelled job {job.name}")
            except Exception:
                pass

    async def check_inactivity(self, context: CallbackContext) -> None:
        """Check all users for inactivity and send re-engagement prompts."""
        today = date.today()
        for user_id, _, _, last_date_str in self.db.get_active_users():
            if last_date_str:
                try:
                    last_date = date.fromisoformat(last_date_str)
                except ValueError:
                    # If invalid date in DB, reset it to today
                    self.db.update_interaction(user_id, today)
                    continue
            else:
                # No interaction recorded yet; treat as inactive since subscription
                last_date = today - timedelta(days=4)
            days_inactive = (today - last_date).days
            if days_inactive >= 3:
                # Send gentle re-engagement message
                reengagement = (
                    "Hey, haven’t seen your check‑ins lately. Everything okay? "
                    "Remember, journaling helps reflect and grow."
                )
                try:
                    await context.bot.send_message(chat_id=user_id, text=reengagement)
                except Exception as exc:
                    logger.warning(f"Failed to send re-engagement message to {user_id}: {exc}")
                # Notify admin if configured
                if self.admin_id:
                    try:
                        await context.bot.send_message(
                            chat_id=self.admin_id,
                            text=f"User {user_id} has been inactive for {days_inactive} days.",
                        )
                    except Exception as exc:
                        logger.warning(f"Failed to alert admin for user {user_id}: {exc}")

    async def run(self) -> None:
        """Start the bot and run until manually stopped."""
        # Schedule reminder jobs for all existing active users on startup
        for user_id, _, _, _ in self.db.get_active_users():
            await self.schedule_user_reminders(user_id)
        logger.info("Bot started and ready to accept updates.")
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        # Run forever unless cancelled
        await self.application.updater.idle()


def main() -> None:
    """Entry point of the bot when run as a script."""
    load_dotenv()
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "BOT_TOKEN is not set. Define it in a .env file or environment variables."
        )
    admin_id = os.environ.get("ADMIN_ID")
    bot = ValenBot(token=token, admin_id=admin_id)
    try:
        asyncio.run(bot.run())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")


if __name__ == "__main__":
    main()