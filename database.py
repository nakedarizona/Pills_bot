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
                frequency TEXT DEFAULT 'daily',
                interval_days INTEGER DEFAULT 1,
                start_date TEXT,
                is_active BOOLEAN DEFAULT 1,
                FOREIGN KEY (pill_id) REFERENCES pills (id) ON DELETE CASCADE
            )
        """)

        # Add new columns if they don't exist (migration)
        try:
            await db.execute("ALTER TABLE schedules ADD COLUMN frequency TEXT DEFAULT 'daily'")
        except:
            pass
        try:
            await db.execute("ALTER TABLE schedules ADD COLUMN interval_days INTEGER DEFAULT 1")
        except:
            pass
        try:
            await db.execute("ALTER TABLE schedules ADD COLUMN start_date TEXT")
        except:
            pass

        await db.execute("""
            CREATE TABLE IF NOT EXISTS intake_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                schedule_id INTEGER NOT NULL,
                scheduled_time DATETIME NOT NULL,
                taken_at DATETIME,
                status TEXT DEFAULT 'pending',
                reminder_count INTEGER DEFAULT 0,
                last_reminder_at DATETIME,
                FOREIGN KEY (schedule_id) REFERENCES schedules (id) ON DELETE CASCADE
            )
        """)

        # Add new columns if they don't exist (migration for intake_logs)
        try:
            await db.execute("ALTER TABLE intake_logs ADD COLUMN reminder_count INTEGER DEFAULT 0")
        except:
            pass
        try:
            await db.execute("ALTER TABLE intake_logs ADD COLUMN last_reminder_at DATETIME")
        except:
            pass

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


async def update_pill(
    pill_id: int,
    name: Optional[str] = None,
    dosage: Optional[str] = None,
    photo_id: Optional[str] = None,
) -> bool:
    """Update pill fields."""
    async with aiosqlite.connect(DB_PATH) as db:
        updates = []
        params = []

        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if dosage is not None:
            updates.append("dosage = ?")
            params.append(dosage)
        if photo_id is not None:
            updates.append("photo_id = ?")
            params.append(photo_id)

        if not updates:
            return False

        params.append(pill_id)
        query = f"UPDATE pills SET {', '.join(updates)} WHERE id = ?"
        cursor = await db.execute(query, params)
        await db.commit()
        return cursor.rowcount > 0


# Schedule operations
async def add_schedule(
    pill_id: int,
    time: str,
    days: list[int],
    frequency: str = "daily",
    interval_days: int = 1,
    start_date: Optional[str] = None,
) -> Schedule:
    """Add a schedule for a pill.

    frequency: daily, weekly, monthly, interval, specific_days
    interval_days: used when frequency is 'interval' (e.g., every 2 days)
    start_date: reference date for interval calculations
    """
    if start_date is None:
        start_date = date.today().isoformat()

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO schedules (pill_id, time, days, frequency, interval_days, start_date)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (pill_id, time, json.dumps(days), frequency, interval_days, start_date),
        )
        await db.commit()

        return Schedule(
            id=cursor.lastrowid,
            pill_id=pill_id,
            time=time,
            days=days,
            frequency=frequency,
            interval_days=interval_days,
            start_date=start_date,
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
                frequency=row["frequency"] or "daily",
                interval_days=row["interval_days"] or 1,
                start_date=row["start_date"],
                is_active=bool(row["is_active"]),
            )
            for row in rows
        ]


async def get_schedules_for_time_range(time_from: str, time_to: str, current_date: date) -> list[dict]:
    """Get all active schedules for today within a time range (inclusive)."""
    day_of_week = current_date.isoweekday()
    day_of_month = current_date.day

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT s.*, p.name as pill_name, p.dosage, p.photo_id,
                   u.telegram_id, u.chat_id, u.username, u.first_name
            FROM schedules s
            JOIN pills p ON s.pill_id = p.id
            JOIN users u ON p.user_id = u.id
            WHERE s.time >= ? AND s.time <= ? AND s.is_active = 1
            ORDER BY s.time
            """,
            (time_from, time_to),
        )
        rows = await cursor.fetchall()

        result = []
        for row in rows:
            row_dict = dict(row)
            days = json.loads(row["days"])
            frequency = row["frequency"] or "daily"
            interval_days = row["interval_days"] or 1
            start_date_str = row["start_date"]

            should_remind = False

            if frequency == "daily":
                should_remind = True
            elif frequency == "weekly" or frequency == "specific_days":
                should_remind = day_of_week in days
            elif frequency == "monthly":
                should_remind = day_of_month in days
            elif frequency == "interval":
                if start_date_str:
                    start = date.fromisoformat(start_date_str)
                    days_passed = (current_date - start).days
                    should_remind = days_passed >= 0 and days_passed % interval_days == 0
                else:
                    should_remind = True

            if should_remind:
                result.append(row_dict)

        return result


async def get_schedules_for_time(time_str: str, current_date: date) -> list[dict]:
    """Get all active schedules for a specific time and date."""
    day_of_week = current_date.isoweekday()
    day_of_month = current_date.day

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
            row_dict = dict(row)
            days = json.loads(row["days"])
            frequency = row["frequency"] or "daily"
            interval_days = row["interval_days"] or 1
            start_date_str = row["start_date"]

            should_remind = False

            if frequency == "daily":
                should_remind = True
            elif frequency == "weekly" or frequency == "specific_days":
                should_remind = day_of_week in days
            elif frequency == "monthly":
                should_remind = day_of_month in days
            elif frequency == "interval":
                if start_date_str:
                    start = date.fromisoformat(start_date_str)
                    days_passed = (current_date - start).days
                    should_remind = days_passed >= 0 and days_passed % interval_days == 0
                else:
                    should_remind = True

            if should_remind:
                result.append(row_dict)

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
    day_of_month = today.day

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT s.*, p.name as pill_name, p.dosage, p.photo_id,
                   il.id as log_id, il.status as intake_status, il.taken_at
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
            row_dict = dict(row)
            days = json.loads(row["days"])
            frequency = row["frequency"] or "daily"
            interval_days = row["interval_days"] or 1
            start_date_str = row["start_date"]

            should_show = False

            if frequency == "daily":
                should_show = True
            elif frequency == "weekly" or frequency == "specific_days":
                should_show = day_of_week in days
            elif frequency == "monthly":
                should_show = day_of_month in days
            elif frequency == "interval":
                if start_date_str:
                    start = date.fromisoformat(start_date_str)
                    days_passed = (today - start).days
                    should_show = days_passed >= 0 and days_passed % interval_days == 0
                else:
                    should_show = True

            if should_show:
                result.append(row_dict)

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


async def update_reminder_count(log_id: int, reminder_time: datetime) -> bool:
    """Update reminder count and last reminder time."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            UPDATE intake_logs
            SET reminder_count = reminder_count + 1, last_reminder_at = ?
            WHERE id = ?
            """,
            (reminder_time.isoformat(), log_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_logs_for_followup_reminder(hours_ago: int) -> list[dict]:
    """Get pending logs that need one follow-up reminder after N hours (no response)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT il.*, s.time, s.pill_id, s.frequency, s.interval_days, s.start_date,
                   p.name as pill_name, p.dosage, p.photo_id,
                   u.telegram_id, u.chat_id, u.username, u.first_name
            FROM intake_logs il
            JOIN schedules s ON il.schedule_id = s.id
            JOIN pills p ON s.pill_id = p.id
            JOIN users u ON p.user_id = u.id
            WHERE il.status = 'pending'
              AND date(il.scheduled_time) = date('now')
              AND il.reminder_count = 0
              AND datetime(il.scheduled_time, '+' || ? || ' hours') <= datetime('now')
            """,
            (hours_ago,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def update_schedule_start_date(schedule_id: int, new_start_date: str) -> bool:
    """Update schedule start_date (for interval-based schedules after confirmation)."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE schedules SET start_date = ? WHERE id = ?",
            (new_start_date, schedule_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_intake_logs_by_ids(log_ids: list[int]) -> list[dict]:
    """Get intake logs with pill info by list of IDs."""
    if not log_ids:
        return []
    placeholders = ",".join("?" * len(log_ids))
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            f"""
            SELECT il.id, il.status, il.taken_at, il.schedule_id,
                   p.name as pill_name, p.dosage,
                   s.frequency, s.id as schedule_id,
                   u.telegram_id
            FROM intake_logs il
            JOIN schedules s ON il.schedule_id = s.id
            JOIN pills p ON s.pill_id = p.id
            JOIN users u ON p.user_id = u.id
            WHERE il.id IN ({placeholders})
            ORDER BY il.id
            """,
            log_ids,
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_schedule_by_id(schedule_id: int) -> Optional[dict]:
    """Get schedule by ID with full details."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT s.*, p.name as pill_name, p.dosage, p.photo_id,
                   u.telegram_id, u.chat_id, u.username, u.first_name
            FROM schedules s
            JOIN pills p ON s.pill_id = p.id
            JOIN users u ON p.user_id = u.id
            WHERE s.id = ?
            """,
            (schedule_id,),
        )
        row = await cursor.fetchone()
        if row:
            return dict(row)
        return None
