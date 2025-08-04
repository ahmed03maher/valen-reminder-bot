import sqlite3
from datetime import datetime

DB_PATH = "valen_users.db"

def create_table():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            last_interaction TEXT,
            morning_time TEXT DEFAULT '10:00',
            evening_time TEXT DEFAULT '22:00'
        )
        """)
        conn.commit()

def add_user(user_id):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT OR IGNORE INTO users (user_id, last_interaction)
        VALUES (?, ?)
        """, (user_id, datetime.utcnow().isoformat()))
        conn.commit()

def update_last_interaction(user_id):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        UPDATE users SET last_interaction = ? WHERE user_id = ?
        """, (datetime.utcnow().isoformat(), user_id))
        conn.commit()

def get_last_interaction(user_id):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT last_interaction FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        return row[0] if row else None

def set_user_time(user_id, time_type, time_str):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
        UPDATE users SET {time_type}_time = ? WHERE user_id = ?
        """, (time_str, user_id))
        conn.commit()

def get_user_times(user_id):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT morning_time, evening_time FROM users WHERE user_id = ?
        """, (user_id,))
        row = cursor.fetchone()
        return row if row else ('10:00', '22:00')

def get_all_users():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, morning_time, evening_time FROM users")
        return cursor.fetchall()
