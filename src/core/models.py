"""
Data models for the Pomodoro + Calendar + Memo application.
All models serialize to/from plain dicts for JSON storage.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional
from datetime import datetime
import uuid


def new_id() -> str:
    return str(uuid.uuid4())[:8]


# ---------------------------------------------------------------------------
# Memo / Four-Quadrant
# ---------------------------------------------------------------------------

QUADRANTS = {
    1: "重要且紧急",
    2: "重要不紧急",
    3: "紧急不重要",
    4: "不重要不紧急",
}


@dataclass
class MemoTask:
    id: str = field(default_factory=new_id)
    title: str = ""
    note: str = ""
    quadrant: int = 2          # 1-4
    done: bool = False
    deleted: bool = False
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    # Recurring schedule — empty string means no schedule
    # Format: "daily|HH:MM|DUR_MIN|YYYY-MM-DD"
    #      or "weekly-N|HH:MM|DUR_MIN|YYYY-MM-DD"   N=0(Mon)…6(Sun)
    #      or "monthly-D|HH:MM|DUR_MIN|YYYY-MM-DD"  D=day-of-month 1..31
    # YYYY-MM-DD is the schedule end date (inclusive)
    schedule: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "MemoTask":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# Calendar time blocks
# ---------------------------------------------------------------------------

@dataclass
class TimeBlock:
    id: str = field(default_factory=new_id)
    title: str = ""
    date: str = ""             # "YYYY-MM-DD"
    start_time: str = ""       # "HH:MM"
    end_time: str = ""         # "HH:MM"
    memo_task_id: Optional[str] = None
    is_planned: bool = False   # True = future planned, False = completed/manual
    color: str = "#4A90D9"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "TimeBlock":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# Pomodoro session
# ---------------------------------------------------------------------------

@dataclass
class PomodoroSegment:
    """One work or break segment within a session."""
    duration_min: int = 25
    is_break: bool = False


@dataclass
class PomodoroTemplate:
    """User-configurable sequence of work+break segments."""
    id: str = field(default_factory=new_id)
    name: str = "默认模板"
    # list of dicts {"duration_min": int, "is_break": bool}
    segments: list = field(default_factory=lambda: [
        {"duration_min": 25, "is_break": False},
        {"duration_min": 5,  "is_break": True},
        {"duration_min": 25, "is_break": False},
        {"duration_min": 5,  "is_break": True},
        {"duration_min": 25, "is_break": False},
        {"duration_min": 15, "is_break": True},
    ])

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "PomodoroTemplate":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def total_minutes(self) -> int:
        return sum(s["duration_min"] for s in self.segments)


@dataclass
class PomodoroSession:
    """One scheduled/completed pomodoro run."""
    id: str = field(default_factory=new_id)
    template_id: str = ""
    memo_task_id: Optional[str] = None
    label: str = ""            # free-text label (work / exercise / rest …)
    planned_date: str = ""     # "YYYY-MM-DD"
    planned_start: str = ""    # "HH:MM"
    actual_start: Optional[str] = None
    actual_end: Optional[str] = None
    completed: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "PomodoroSession":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# Sticky notes
# ---------------------------------------------------------------------------

@dataclass
class StickyNote:
    id: str = field(default_factory=new_id)
    title: str = ""
    body: str = ""
    pinned: bool = False
    collapsed: bool = False
    card_height: int = 0          # 0 = auto; >0 = user-set px height
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "StickyNote":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# App settings
# ---------------------------------------------------------------------------

@dataclass
class AlertSettings:
    mode_rest_screen: bool = True
    mode_open_url: bool = False
    url: str = ""
    mode_open_file: bool = False
    file_path: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "AlertSettings":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class AppSettings:
    startup_with_windows: bool = True
    close_to_tray: bool = False        # True=minimize to tray on close, False=exit
    snooze_minutes: int = 10           # last-used snooze value
    default_template_id: str = ""
    alert: AlertSettings = field(default_factory=AlertSettings)
    floaty_pos: list = field(default_factory=lambda: [100, 100])   # [x, y]
    # calendar display settings
    cal_hour_h: int = 64      # pixels per hour in week/day view
    cal_day_w: int = 120      # pixels per day column in week view
    cal_start_h: int = 0      # first hour shown (0-23)
    cal_end_h: int = 24       # last hour shown exclusive (1-24)
    # quadrant header colours (user-customisable)
    quadrant_colors: list = field(default_factory=lambda: [
        "#EF9A9A",   # Q1 重要且紧急
        "#A5D6A7",   # Q2 重要不紧急
        "#FFE082",   # Q3 紧急不重要
        "#CE93D8",   # Q4 不重要不紧急
    ])

    def to_dict(self) -> dict:
        d = asdict(self)
        d["alert"] = self.alert.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "AppSettings":
        alert = AlertSettings.from_dict(d.pop("alert", {}))
        obj = cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
        obj.alert = alert
        return obj
