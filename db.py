"""Слой работы с базой данных (SQLite) для бота «109: Volunteers»."""
import aiosqlite
from datetime import datetime
from math import radians, sin, cos, sqrt, atan2

import config


async def init_db():
    """Создаёт таблицы при первом запуске."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS volunteers (
                user_id     INTEGER PRIMARY KEY,
                full_name   TEXT    NOT NULL,
                age         INTEGER NOT NULL,
                phone       TEXT    NOT NULL,
                lat         REAL,
                lon         REAL,
                points      INTEGER NOT NULL DEFAULT 0,
                done_count  INTEGER NOT NULL DEFAULT 0,
                registered_at TEXT  NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY,
                lang    TEXT NOT NULL DEFAULT 'ru'
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS requests (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id   INTEGER NOT NULL,
                client_name TEXT    NOT NULL,
                client_phone TEXT,
                category    TEXT    NOT NULL,
                description TEXT,
                address     TEXT,
                lat         REAL,
                lon         REAL,
                status      TEXT    NOT NULL DEFAULT 'moderation',
                volunteer_id INTEGER,
                created_at  TEXT    NOT NULL,
                closed_at   TEXT
            )
        """)
        await db.commit()


# ---------- ЯЗЫК ПОЛЬЗОВАТЕЛЯ ----------

async def set_lang(user_id, lang):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO user_settings (user_id, lang) VALUES (?, ?)",
            (user_id, lang),
        )
        await db.commit()


async def get_lang(user_id):
    async with aiosqlite.connect(config.DB_PATH) as db:
        async with db.execute(
            "SELECT lang FROM user_settings WHERE user_id=?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else None


# ---------- ВОЛОНТЁРЫ ----------

async def add_volunteer(user_id, full_name, age, phone, lat=None, lon=None):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            """INSERT OR REPLACE INTO volunteers
               (user_id, full_name, age, phone, lat, lon, points, done_count, registered_at)
               VALUES (?, ?, ?, ?, ?, ?,
                       COALESCE((SELECT points FROM volunteers WHERE user_id=?), 0),
                       COALESCE((SELECT done_count FROM volunteers WHERE user_id=?), 0),
                       ?)""",
            (user_id, full_name, age, phone, lat, lon, user_id, user_id,
             datetime.now().isoformat(timespec="seconds")),
        )
        await db.commit()


async def get_volunteer(user_id):
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM volunteers WHERE user_id=?", (user_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def update_volunteer_location(user_id, lat, lon):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("UPDATE volunteers SET lat=?, lon=? WHERE user_id=?", (lat, lon, user_id))
        await db.commit()


async def add_points(user_id, points):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "UPDATE volunteers SET points = points + ?, done_count = done_count + 1 WHERE user_id=?",
            (points, user_id),
        )
        await db.commit()


async def all_volunteers():
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM volunteers ORDER BY points DESC") as cur:
            return [dict(r) for r in await cur.fetchall()]


async def volunteer_rank(user_id):
    """Место волонтёра в рейтинге по баллам (1 — лучший)."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        async with db.execute(
            """SELECT COUNT(*) + 1 FROM volunteers
               WHERE points > (SELECT points FROM volunteers WHERE user_id=?)""",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else None


# ---------- ЗАЯВКИ ----------

async def add_request(client_id, client_name, client_phone, category, description, address, lat, lon):
    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO requests
               (client_id, client_name, client_phone, category, description, address, lat, lon, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'moderation', ?)""",
            (client_id, client_name, client_phone, category, description, address, lat, lon,
             datetime.now().isoformat(timespec="seconds")),
        )
        await db.commit()
        return cur.lastrowid


async def get_request(req_id):
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM requests WHERE id=?", (req_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def set_request_status(req_id, status, volunteer_id=None):
    async with aiosqlite.connect(config.DB_PATH) as db:
        if status == "open":
            await db.execute("UPDATE requests SET status='open' WHERE id=?", (req_id,))
        elif status == "taken":
            await db.execute("UPDATE requests SET status='taken', volunteer_id=? WHERE id=?",
                             (volunteer_id, req_id))
        elif status == "await_confirm":
            await db.execute("UPDATE requests SET status='await_confirm' WHERE id=?", (req_id,))
        elif status == "done":
            await db.execute("UPDATE requests SET status='done', closed_at=? WHERE id=?",
                             (datetime.now().isoformat(timespec="seconds"), req_id))
        elif status == "rejected":
            await db.execute("UPDATE requests SET status='rejected' WHERE id=?", (req_id,))
        await db.commit()


async def open_requests():
    """Открытые (одобренные, ещё не взятые) заявки."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM requests WHERE status='open' ORDER BY created_at") as cur:
            return [dict(r) for r in await cur.fetchall()]


async def requests_by_status(status):
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM requests WHERE status=? ORDER BY created_at", (status,)) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def all_requests():
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM requests ORDER BY id") as cur:
            return [dict(r) for r in await cur.fetchall()]


# ---------- ГЕО ----------

def haversine_km(lat1, lon1, lat2, lon2):
    """Расстояние между двумя точками в км."""
    if None in (lat1, lon1, lat2, lon2):
        return float("inf")
    r = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return r * 2 * atan2(sqrt(a), sqrt(1 - a))
