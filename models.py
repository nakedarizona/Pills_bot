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
    is_active: bool = True

    @property
    def days_json(self) -> str:
        return json.dumps(self.days)

    @classmethod
    def days_from_json(cls, json_str: str) -> list[int]:
        return json.loads(json_str)


@dataclass
class IntakeLog:
    id: int
    schedule_id: int
    scheduled_time: datetime
    taken_at: Optional[datetime] = None
    status: str = "pending"  # pending, taken, missed, reminded
