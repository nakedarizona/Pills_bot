import aiosqlite
import json
from datetime import datetime, date
from typing import Optional
from config import DB_PATH
from models import User, Pill, Schedule, IntakeLog


async def init_db():
    """Initialize database and create tables if not exist."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                username TEXT,
                first_name TEXT,
                timezone TEXT DEFAULT 'Europe/Moscow',
                UNIQUE(telegram_id, chat_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS pills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                dosage TEXT NOT NULL,
                photo_id TEXT,
                notes TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pill_id INTEGER NOT NULL,
                time TEXT NOT NULL,
                days TEXT NOT NULL,
                is_active BOOLEAN DEFAULT 1,
                FOREIGN KEY (pill_id) REFERENCES pills (id) ON DELETE CASCADE
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS intake_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                schedule_id INTEGER NOT NULL,
                scheduled_time DATETIME NOT NULL,
                taken_at DATETIME,
                status TEXT DEFAULT 'pending',
                FOREIGN KEY (schedule_id) REFERENCES schedules (id) ON DELETE CASCADE
            )
        """)

        await db.commit()


# User operations
async def get_or_create_user(
    telegram_id: int,
    chat_id: int,
    username: Optional[str],
    first_name: Optional[str],
) -> User:
    """Get existing user or create new one."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM users WHERE telegram_id = ? AND chat_id = ?",
            (telegram_id, chat_id),
        )
        row = await cursor.fetchone()

        if row:
            return User(
                id=row["id"],
                telegram_id=row["telegram_id"],
                chat_id=row["chat_id"],
                username=row["username"],
                first_name=row["first_name"],
                timezone=row["timezone"],
            )

        cursor = await db.execute(
            """INSERT INTO users (telegram_id, chat_id, username, first_name)
               VALUES (?, ?, ?, ?)""",
            (telegram_id, chat_id, username, first_name),
        )
        await db.commit()

        return User(
            id=cursor.lastrowid,
            telegram_id=telegram_id,
            chat_id=chat_id,
            username=username,
            first_name=first_name,
        )


async def get_user(telegram_id: int, chat_id: int) -> Optional[User]:
    """Get user by telegram_id and chat_id."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM users WHERE telegram_id = ? AND chat_id = ?",
            (telegram_id, chat_id),
        )
        row = await cursor.fetchone()

        if row:
            return User(
                id=row["id"],
                telegram_id=row["telegram_id"],
                chat_id=row["chat_id"],
                username=row["username"],
                first_name=row["first_name"],
                timezone=row["timezone"],
            )
        return None


# Pill operations
async def add_pill(
    user_id: int,
    name: str,
    dosage: str,
    photo_id: Optional[str] = None,
    notes: Optional[str] = None,
) -> Pill:
    """Add a new pill."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO pills (user_id, name, dosage, photo_id, notes)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, name, dosage, photo_id, notes),
        )
        await db.commit()

        return Pill(
            id=cursor.lastrowid,
            user_id=user_id,
            name=name,
            dosage=dosage,
            photo_id=photo_id,
            notes=notes,
        )


async def get_user_pills(user_id: int) -> list[Pill]:
    """Get all pills for a user."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM pills WHERE user_id = ?", (user_id,)
        )
        rows = await cursor.fetchall()

        return [
            Pill(
                id=row["id"],
                user_id=row["user_id"],
                name=row["name"],
                dosage=row["dosage"],
                photo_id=row["photo_id"],
                notes=row["notes"],
            )
            for row in rows
        ]


async def get_pill(pill_id: int) -> Optional[Pill]:
    """Get pill by id."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM pills WHERE id = ?", (pill_id,))
        row = await cursor.fetchone()

        if row:
            return Pill(
                id=row["id"],
                user_id=row["user_id"],
                name=row["name"],
                dosage=row["dosage"],
                photo_id=row["photo_id"],
                notes=row["notes"],
            )
        return None


async def delete_pill(pill_id: int) -> bool:
    """Delete a pill and its schedules."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("DELETE FROM pills WHERE id = ?", (pill_id,))
        await db.commit()
        return cursor.rowcount > 0


# Schedule operations
async def add_schedule(
    pill_id: int, time: str, days: list[int]
) -> Schedule:
    """Add a schedule for a pill."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO schedules (pill_id, time, days)
               VALUES (?, ?, ?)""",
            (pill_id, time, json.dumps(days)),
        )
        await db.commit()

        return Schedule(
            id=cursor.lastrowid, pill_id=pill_id, time=time, days=days
        )


async def get_pill_schedules(pill_id: int) -> list[Schedule]:
    """Get all schedules for a pill."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM schedules WHERE pill_id = ? AND is_active = 1",
            (pill_id,),
        )
        rows = await cursor.fetchall()

        return [
            Schedule(
                id=row["id"],
                pill_id=row["pill_id"],
                time=row["time"],
                days=json.loads(row["days"]),
                is_active=bool(row["is_active"]),
            )
            for row in rows
        ]


async def get_schedules_for_time(time_str: str, day_of_week: int) -> list[dict]:
    """Get all active schedules for a specific time and day."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT s.*, p.name as pill_name, p.dosage, p.photo_id,
                   u.telegram_id, u.chat_id, u.username, u.first_name
            FROM schedules s
            JOIN pills p ON s.pill_id = p.id
            JOIN users u ON p.user_id = u.id
            WHERE s.time = ? AND s.is_active = 1
            """,
            (time_str,),
        )
        rows = await cursor.fetchall()

        result = []
        for row in rows:
            days = json.loads(row["days"])
            if day_of_week in days:
                result.append(dict(row))
        return result


async def delete_schedule(schedule_id: int) -> bool:
    """Delete a schedule."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM schedules WHERE id = ?", (schedule_id,)
        )
        await db.commit()
        return cursor.rowcount > 0


# Intake log operations
async def create_intake_log(schedule_id: int, scheduled_time: datetime) -> IntakeLog:
    """Create an intake log entry."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO intake_logs (schedule_id, scheduled_time, status)
               VALUES (?, ?, 'pending')""",
            (schedule_id, scheduled_time.isoformat()),
        )
        await db.commit()

        return IntakeLog(
            id=cursor.lastrowid,
            schedule_id=schedule_id,
            scheduled_time=scheduled_time,
        )


async def get_intake_log(log_id: int) -> Optional[IntakeLog]:
    """Get intake log by id."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM intake_logs WHERE id = ?", (log_id,)
        )
        row = await cursor.fetchone()

        if row:
            return IntakeLog(
                id=row["id"],
                schedule_id=row["schedule_id"],
                scheduled_time=datetime.fromisoformat(row["scheduled_time"]),
                taken_at=(
                    datetime.fromisoformat(row["taken_at"])
                    if row["taken_at"]
                    else None
                ),
                status=row["status"],
            )
        return None


async def update_intake_status(
    log_id: int, status: str, taken_at: Optional[datetime] = None
) -> bool:
    """Update intake log status."""
    async with aiosqlite.connect(DB_PATH) as db:
        if taken_at:
            cursor = await db.execute(
                "UPDATE intake_logs SET status = ?, taken_at = ? WHERE id = ?",
                (status, taken_at.isoformat(), log_id),
            )
        else:
            cursor = await db.execute(
                "UPDATE intake_logs SET status = ? WHERE id = ?", (status, log_id)
            )
        await db.commit()
        return cursor.rowcount > 0


async def get_pending_logs_for_today(chat_id: int) -> list[dict]:
    """Get all pending intake logs for today for a specific chat."""
    today = date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT il.*, s.time, p.name as pill_name, p.dosage,
                   u.telegram_id, u.username, u.first_name
            FROM intake_logs il
            JOIN schedules s ON il.schedule_id = s.id
            JOIN pills p ON s.pill_id = p.id
            JOIN users u ON p.user_id = u.id
            WHERE u.chat_id = ?
              AND il.status = 'pending'
              AND date(il.scheduled_time) = ?
            """,
            (chat_id, today),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_user_today_schedule(user_id: int) -> list[dict]:
    """Get today's schedule for a user with intake status."""
    today = date.today()
    day_of_week = today.isoweekday()

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT s.*, p.name as pill_name, p.dosage, p.photo_id,
                   il.id as log_id, il.status as intake_status
            FROM schedules s
            JOIN pills p ON s.pill_id = p.id
            LEFT JOIN intake_logs il ON s.id = il.schedule_id
                AND date(il.scheduled_time) = ?
            WHERE p.user_id = ? AND s.is_active = 1
            ORDER BY s.time
            """,
            (today.isoformat(), user_id),
        )
        rows = await cursor.fetchall()

        result = []
        for row in rows:
            days = json.loads(row["days"])
            if day_of_week in days:
                result.append(dict(row))
        return result


async def check_existing_log(schedule_id: int, scheduled_date: date) -> bool:
    """Check if intake log already exists for schedule and date."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT id FROM intake_logs
            WHERE schedule_id = ? AND date(scheduled_time) = ?
            """,
            (schedule_id, scheduled_date.isoformat()),
        )
        row = await cursor.fetchone()
        return row is not None
