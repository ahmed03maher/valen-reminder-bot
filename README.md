# Valen Journal Reminder Bot

This repository contains the source code for a Telegram bot that sends
daily journaling reminders to users of the **Valen** journaling product.
The bot allows users to subscribe via `/start`, receive two daily
reminders (10 AM and 10 PM by default), track interactions, gently
re‑engage inactive users, and alert an administrator when someone stops
checking in.

## Features

* **Subscribe/Unsubscribe** – Users send `/start` to begin receiving
  reminders and `/stop` to opt out. Reminder times can be customised in
  the future; currently they default to 10 AM and 10 PM in the
  Africa/Cairo timezone.
* **Daily Reminders** – Two scheduled messages encourage journal
  entries. Users can reply or react to log an interaction.
* **Inactivity Detection** – If a user does not reply to any reminder
  for three consecutive days, the bot sends a friendly prompt asking if
  everything is okay. At the same time, the administrator (if
  configured) is notified of the user’s inactivity.
* **SQLite Persistence** – Subscriber details and last interaction dates
  are stored in a local SQLite database (`valen.db`).
* **Deployment Ready** – Designed to be deployed on cloud providers
  such as [Render](https://render.com) or
  [Railway](https://railway.app) with minimal configuration.

## Getting Started

### Prerequisites

* Python 3.10 or later
* A Telegram bot token from [BotFather](https://t.me/botfather)

### Installation

1. **Clone the repository**

   ```bash
   git clone <your-fork-url>
   cd valen_bot
   ```

2. **Create a virtual environment** (recommended)

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

4. **Configuration**

   Copy `.env.example` to `.env` and fill in your Telegram bot token
   (and optionally your admin user ID):

   ```bash
   cp .env.example .env
   # Then edit .env with your favourite editor
   ```

5. **Run the bot**

   ```bash
   python -m valen_bot.bot
   ```

The bot will subscribe users on `/start`, schedule reminders, and
persist data to `valen.db` in the project root.

## Deployment

This project is ready to deploy on services such as Render or Railway.
Both platforms support running long‑lived processes and setting
environment variables.

### Railway

1. Push your repository to a Git provider (GitHub/GitLab).
2. Create a new Railway project and link your repository.
3. In the Railway dashboard, add the following **Environment Variables**:
   - `BOT_TOKEN` – your Telegram bot token.
   - `ADMIN_ID` – your personal Telegram user ID (optional).
4. Set the **Start Command** to:

   ```bash
   python -m valen_bot.bot
   ```

5. Deploy the service. Railway will install dependencies from
   `requirements.txt` and run the bot.

### Render

1. Push your repository to GitHub.
2. Create a new **Web Service** on Render and choose your repo.
3. Under **Environment**, add `BOT_TOKEN` and optionally `ADMIN_ID`.
4. Set the **Build Command** to:

   ```bash
   pip install -r requirements.txt
   ```

5. Set the **Start Command** to:

   ```bash
   python -m valen_bot.bot
   ```

6. Deploy. Render will start the bot as a continuously running service.

## Customising Reminder Times

At present, reminder times are fixed at **10 AM** and **10 PM** in the
Africa/Cairo timezone. To enable per‑user customisation you can extend
the `/start` command to prompt users for their preferred hours and
update the database accordingly. All scheduling logic lives in
`ValenBot.schedule_user_reminders` in `bot.py`.

## Testing

To test the bot locally without deploying:

1. Create a bot with BotFather and obtain its token.
2. Fill in `.env` with your token and your Telegram user ID as the
   `ADMIN_ID` (so you receive inactivity alerts).
3. Run the bot. Interact with it from your Telegram account. Use
   `/start` to subscribe, wait for reminders at the scheduled times
   (10 AM and 10 PM), reply with messages or emojis to record
   interactions, and verify that inactivity alerts fire after three days
   of no responses.

Because the inactivity check runs once a day at 09:00 (Africa/Cairo),
you can shorten the three‑day interval in `bot.py` for quicker testing.

## License

This project is provided under the MIT License. See `LICENSE` for
details.