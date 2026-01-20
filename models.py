from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import json


@dataclass
class User:
    id: int
    telegram_id: int
    chat_id: int
    username: Optional[str]
    first_name: Optional[str]
    timezone: str = "Europe/Moscow"


@dataclass
class Pill:
    id: int
    user_id: int
    name: str
    dosage: str
    photo_id: Optional[str] = None
    notes: Optional[str] = None


@dataclass
class Schedule:
    id: int
    pill_id: int
    time: str  # HH:MM format
    days: list[int]  # 1-7 for Monday-Sunday
    frequency: str = "daily"  # daily, weekly, monthly, interval, specific_days
    interval_days: int = 1  # for interval frequency
    start_date: Optional[str] = None  # YYYY-MM-DD
    is_active: bool = True

    @property
    def days_json(self) -> str:
        return json.dumps(self.days)

    @classmethod
    def days_from_json(cls, json_str: str) -> list[int]:
        return json.loads(json_str)

    def get_frequency_display(self) -> str:
        """Human-readable frequency."""
        if self.frequency == "daily":
            return "ежедневно"
        elif self.frequency == "weekly":
            day_names = {1: "Пн", 2: "Вт", 3: "Ср", 4: "Чт", 5: "Пт", 6: "Сб", 7: "Вс"}
            days_str = ", ".join(day_names[d] for d in sorted(self.days))
            return f"раз в неделю ({days_str})"
        elif self.frequency == "monthly":
            return f"раз в месяц ({self.days[0]} числа)" if self.days else "раз в месяц"
        elif self.frequency == "interval":
            if self.interval_days == 2:
                return "через день"
            return f"каждые {self.interval_days} дн."
        elif self.frequency == "specific_days":
            day_names = {1: "Пн", 2: "Вт", 3: "Ср", 4: "Чт", 5: "Пт", 6: "Сб", 7: "Вс"}
            days_str = ", ".join(day_names[d] for d in sorted(self.days))
            return days_str
        return "неизвестно"


@dataclass
class IntakeLog:
    id: int
    schedule_id: int
    scheduled_time: datetime
    taken_at: Optional[datetime] = None
    status: str = "pending"  # pending, taken, missed, reminded
