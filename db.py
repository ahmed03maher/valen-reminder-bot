"""
Database helper module for the Valen Telegram bot.

This module wraps basic SQLite operations needed by the bot to
persist user subscriptions and activity metadata. The bot stores
each user who subscribes via `/start` along with their preferred
reminder times and the date of their last interaction. When a user
unsubscribes via `/stop` they are removed from the database.

SQLite is used instead of a flat JSON file because it offers
concurrency control and richer querying capabilities without
introducing an external dependency. The database schema is
automatically created if it does not yet exist when the bot
initialises.
"""

import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path
from typing import Iterable, Optional, Tuple


class Database:
    """Simple wrapper around a SQLite database for persisting user data."""

    def __init__(self, db_path: str = "valen.db") -> None:
        self.db_path = Path(db_path)
        self._initialise()

    def _initialise(self) -> None:
        """Create the database and tables if they don't already exist."""
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    reminder_hour_1 INTEGER NOT NULL,
                    reminder_hour_2 INTEGER NOT NULL,
                    last_interaction_date TEXT,
                    subscribed INTEGER NOT NULL DEFAULT 1
                )
                """
            )

    # -- CRUD operations -----------------------------------------------------

    def add_user(self, user_id: int, hour1: int = 10, hour2: int = 22) -> None:
        """Insert or replace a user in the database.

        If the user already exists their reminder hours will be updated and
        subscription flag reset to active.

        Args:
            user_id: Telegram user identifier
            hour1: hour of the first daily reminder (0-23)
            hour2: hour of the second daily reminder (0-23)
        """
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute(
                """
                INSERT INTO users (user_id, reminder_hour_1, reminder_hour_2, last_interaction_date, subscribed)
                VALUES (?, ?, ?, NULL, 1)
                ON CONFLICT(user_id) DO UPDATE SET
                    reminder_hour_1=excluded.reminder_hour_1,
                    reminder_hour_2=excluded.reminder_hour_2,
                    subscribed=1
                """,
                (user_id, hour1, hour2),
            )

    def remove_user(self, user_id: int) -> None:
        """Mark a user as unsubscribed.

        We do not delete the user outright to preserve their historical
        data; instead the `subscribed` flag is set to zero. Unsubscribed
        users are ignored when scheduling reminders.
        """
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute(
                "UPDATE users SET subscribed=0 WHERE user_id=?",
                (user_id,),
            )

    def update_interaction(self, user_id: int, interaction_date: Optional[date] = None) -> None:
        """Record the date of the latest user interaction.

        Args:
            user_id: Telegram user identifier
            interaction_date: date of the interaction; defaults to today
        """
        if interaction_date is None:
            interaction_date = date.today()
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute(
                "UPDATE users SET last_interaction_date=? WHERE user_id=?",
                (interaction_date.isoformat(), user_id),
            )

    def get_user(self, user_id: int) -> Optional[Tuple[int, int, int, Optional[str], int]]:
        """Return a single user's record or None if it doesn't exist."""
        with closing(sqlite3.connect(self.db_path)) as conn:
            cursor = conn.execute(
                "SELECT user_id, reminder_hour_1, reminder_hour_2, last_interaction_date, subscribed FROM users WHERE user_id=?",
                (user_id,),
            )
            row = cursor.fetchone()
            return row if row else None

    def get_active_users(self) -> Iterable[Tuple[int, int, int, Optional[str]]]:
        """Return an iterable of (user_id, hour1, hour2, last_interaction_date) for subscribed users."""
        with closing(sqlite3.connect(self.db_path)) as conn:
            cursor = conn.execute(
                "SELECT user_id, reminder_hour_1, reminder_hour_2, last_interaction_date FROM users WHERE subscribed=1"
            )
            return list(cursor.fetchall())
