import sqlite3
import threading
from typing import Optional

DB_PATH = "voidflame.db"
_lock = threading.Lock()


def connect():
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with _lock:
        con = connect()
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id INTEGER PRIMARY KEY,
                log_channel_id INTEGER,
                warning_channel_id INTEGER,
                staff_channel_id INTEGER,
                protection_enabled INTEGER NOT NULL DEFAULT 1,
                ai_enabled INTEGER NOT NULL DEFAULT 1,
                raid_enabled INTEGER NOT NULL DEFAULT 1,
                spam_enabled INTEGER NOT NULL DEFAULT 1,
                link_enabled INTEGER NOT NULL DEFAULT 1,
                mention_enabled INTEGER NOT NULL DEFAULT 1,
                webhook_enabled INTEGER NOT NULL DEFAULT 1,
                nuke_enabled INTEGER NOT NULL DEFAULT 1,
                lockdown_enabled INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS trusted_users (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            );
            """
        )
        # Safe migrations for databases created by an older version.
        columns = {row[1] for row in con.execute("PRAGMA table_info(guild_settings)").fetchall()}
        migrations = {
            "mention_enabled": "INTEGER NOT NULL DEFAULT 1",
            "webhook_enabled": "INTEGER NOT NULL DEFAULT 1",
            "nuke_enabled": "INTEGER NOT NULL DEFAULT 1",
            "lockdown_enabled": "INTEGER NOT NULL DEFAULT 1",
        }
        for name, definition in migrations.items():
            if name not in columns:
                con.execute(f"ALTER TABLE guild_settings ADD COLUMN {name} {definition}")
        con.commit()
        con.close()


def ensure_guild(guild_id: int):
    with _lock:
        con = connect()
        con.execute("INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)", (guild_id,))
        con.commit()
        con.close()


def set_channel(guild_id: int, field: str, channel_id: Optional[int]):
    allowed = {"log_channel_id", "warning_channel_id", "staff_channel_id"}
    if field not in allowed:
        raise ValueError("Invalid channel setting")
    ensure_guild(guild_id)
    with _lock:
        con = connect()
        con.execute(f"UPDATE guild_settings SET {field}=? WHERE guild_id=?", (channel_id, guild_id))
        con.commit()
        con.close()


def get_settings(guild_id: int) -> dict:
    ensure_guild(guild_id)
    con = connect()
    row = con.execute("SELECT * FROM guild_settings WHERE guild_id=?", (guild_id,)).fetchone()
    con.close()
    return dict(row) if row else {}


def set_toggle(guild_id: int, field: str, value: bool):
    allowed = {
        "protection_enabled", "ai_enabled", "raid_enabled", "spam_enabled",
        "link_enabled", "mention_enabled", "webhook_enabled", "nuke_enabled", "lockdown_enabled"
    }
    if field not in allowed:
        raise ValueError("Invalid toggle")
    ensure_guild(guild_id)
    with _lock:
        con = connect()
        con.execute(f"UPDATE guild_settings SET {field}=? WHERE guild_id=?", (int(value), guild_id))
        con.commit()
        con.close()


def add_trusted(guild_id: int, user_id: int):
    with _lock:
        con = connect()
        con.execute("INSERT OR IGNORE INTO trusted_users VALUES (?, ?)", (guild_id, user_id))
        con.commit()
        con.close()


def remove_trusted(guild_id: int, user_id: int):
    with _lock:
        con = connect()
        con.execute("DELETE FROM trusted_users WHERE guild_id=? AND user_id=?", (guild_id, user_id))
        con.commit()
        con.close()


def is_trusted(guild_id: int, user_id: int) -> bool:
    con = connect()
    row = con.execute("SELECT 1 FROM trusted_users WHERE guild_id=? AND user_id=?", (guild_id, user_id)).fetchone()
    con.close()
    return row is not None
