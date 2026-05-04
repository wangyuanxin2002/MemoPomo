"""
Persistent JSON store – single source of truth for all app data.
Thread-safe for reads; writes always go through save().
"""

import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional

from src.core.models import (
    AppSettings, MemoTask, TimeBlock,
    PomodoroTemplate, PomodoroSession,
)

# When frozen by PyInstaller, store data next to the .exe.
# When running from source, store data in the repo root.
if getattr(sys, 'frozen', False):
    _BASE = Path(sys.executable).parent
else:
    _BASE = Path(__file__).parent.parent.parent

DATA_DIR = _BASE / "data"
SETTINGS_FILE      = DATA_DIR / "settings.json"
MEMO_FILE          = DATA_DIR / "memo.json"
CALENDAR_FILE      = DATA_DIR / "calendar.json"
POMODORO_FILE      = DATA_DIR / "pomodoro.json"
TEMPLATES_FILE     = DATA_DIR / "templates.json"
WORD_PROGRESS_FILE = DATA_DIR / "word_progress.json"


def _load(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return default


def _save(path: Path, data):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _add_min(hm: str, minutes: int) -> str:
    h, m = map(int, hm.split(":"))
    total = h * 60 + m + minutes
    return f"{(total // 60) % 24:02d}:{total % 60:02d}"


# ---------------------------------------------------------------------------
# Schedule parsing helpers
# ---------------------------------------------------------------------------

def parse_schedule(sched: str):
    """
    Parse a MemoTask.schedule string.
    Format: "<freq>|<HH:MM>|<dur_min>|<end_date>"
    freq: "daily", "weekly-N" (N=0..6, Mon=0), "monthly-D" (D=1..31)
    Returns (freq_str, time_str, dur_min, end_date) or None on error.
    """
    if not sched:
        return None
    parts = sched.split("|")
    if len(parts) != 4:
        return None
    try:
        freq, time_str, dur_min_str, end_date_str = parts
        dur_min = int(dur_min_str)
        end_date = date.fromisoformat(end_date_str)
        return freq, time_str, dur_min, end_date
    except Exception:
        return None


def schedule_occurs_on(freq: str, d: date) -> bool:
    """Return True if the recurring schedule fires on date d."""
    if freq == "daily":
        return True
    if freq.startswith("weekly-"):
        n = int(freq.split("-")[1])
        return d.weekday() == n
    if freq.startswith("monthly-"):
        day = int(freq.split("-")[1])
        return d.day == day
    return False


class Store:
    """Central in-memory store with persistence."""

    def __init__(self):
        self._settings: AppSettings = AppSettings()
        self._memo: List[MemoTask] = []
        self._blocks: List[TimeBlock] = []
        self._sessions: List[PomodoroSession] = []
        self._templates: List[PomodoroTemplate] = []
        self._word_progress: dict = {}
        self.load_all()

    # ------------------------------------------------------------------
    # Load / Save
    # ------------------------------------------------------------------

    def load_all(self):
        raw = _load(SETTINGS_FILE, {})
        self._settings = AppSettings.from_dict(raw) if raw else AppSettings()

        self._memo = [MemoTask.from_dict(d) for d in _load(MEMO_FILE, [])]
        self._blocks = [TimeBlock.from_dict(d) for d in _load(CALENDAR_FILE, [])]
        self._sessions = [PomodoroSession.from_dict(d) for d in _load(POMODORO_FILE, [])]

        raw_tpl = _load(TEMPLATES_FILE, [])
        self._templates = [PomodoroTemplate.from_dict(d) for d in raw_tpl]
        if not self._templates:
            default = PomodoroTemplate()
            self._templates = [default]
            self._settings.default_template_id = default.id
            self.save_all()

        self._word_progress = _load(WORD_PROGRESS_FILE, {})
        self._sync_recurring_blocks()

    def save_all(self):
        _save(SETTINGS_FILE,  self._settings.to_dict())
        _save(MEMO_FILE,      [t.to_dict() for t in self._memo])
        _save(CALENDAR_FILE,  [b.to_dict() for b in self._blocks])
        _save(POMODORO_FILE,  [s.to_dict() for s in self._sessions])
        _save(TEMPLATES_FILE, [t.to_dict() for t in self._templates])

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    @property
    def settings(self) -> AppSettings:
        return self._settings

    def save_settings(self):
        _save(SETTINGS_FILE, self._settings.to_dict())

    # ------------------------------------------------------------------
    # Memo
    # ------------------------------------------------------------------

    @property
    def memo_tasks(self) -> List[MemoTask]:
        return self._memo

    def add_memo(self, task: MemoTask):
        self._memo.append(task)
        _save(MEMO_FILE, [t.to_dict() for t in self._memo])

    def update_memo(self, task: MemoTask):
        for i, t in enumerate(self._memo):
            if t.id == task.id:
                self._memo[i] = task
                break
        _save(MEMO_FILE, [t.to_dict() for t in self._memo])
        # re-sync recurring blocks if schedule changed
        self._sync_recurring_blocks()
        _save(CALENDAR_FILE, [b.to_dict() for b in self._blocks])

    def delete_memo(self, task_id: str):
        self._memo = [t for t in self._memo if t.id != task_id]
        _save(MEMO_FILE, [t.to_dict() for t in self._memo])
        # cascade-delete all blocks linked to this task
        self._blocks = [b for b in self._blocks if b.memo_task_id != task_id]
        _save(CALENDAR_FILE, [b.to_dict() for b in self._blocks])

    # ------------------------------------------------------------------
    # Recurring block generation
    # ------------------------------------------------------------------

    def _sync_recurring_blocks(self):
        """
        For each MemoTask with a schedule, ensure all TimeBlocks for dates
        from today through the schedule end_date (up to 180 days out) exist.
        Stale recurring blocks for tasks whose schedule was removed are pruned.
        """
        today = date.today()
        horizon = today + timedelta(days=180)

        # collect task_ids that have schedules and their parsed data
        scheduled: dict[str, tuple] = {}   # task_id → (freq, time_str, dur_min, end_date)
        for task in self._memo:
            parsed = parse_schedule(task.schedule)
            if parsed:
                scheduled[task.id] = parsed

        # remove recurring blocks for tasks that no longer have a schedule
        # (identified by is_planned=True and memo_task_id not in scheduled)
        # We distinguish recurring from normal planned blocks by the
        # presence of a memo_task_id AND the task having a schedule
        def _is_recurring_block(b: TimeBlock) -> bool:
            return b.memo_task_id is not None and b.memo_task_id not in scheduled

        # keep non-recurring blocks and blocks whose task still has a schedule
        self._blocks = [b for b in self._blocks if not _is_recurring_block(b)]

        # build set of (task_id, date_str) already present
        existing: set[tuple] = set()
        for b in self._blocks:
            if b.memo_task_id in scheduled:
                existing.add((b.memo_task_id, b.date))

        # generate missing blocks
        new_blocks: List[TimeBlock] = []
        for task_id, (freq, time_str, dur_min, end_date) in scheduled.items():
            task = next((t for t in self._memo if t.id == task_id), None)
            if not task:
                continue
            cap = min(end_date, horizon)
            cur = today
            while cur <= cap:
                if schedule_occurs_on(freq, cur) and (task_id, cur.isoformat()) not in existing:
                    new_blocks.append(TimeBlock(
                        title=task.title,
                        date=cur.isoformat(),
                        start_time=time_str,
                        end_time=_add_min(time_str, dur_min),
                        memo_task_id=task_id,
                        is_planned=True,
                    ))
                cur += timedelta(days=1)

        self._blocks.extend(new_blocks)

    # ------------------------------------------------------------------
    # Calendar blocks
    # ------------------------------------------------------------------

    @property
    def time_blocks(self) -> List[TimeBlock]:
        return self._blocks

    def blocks_for_week(self, dates: List[str]) -> List[TimeBlock]:
        return [b for b in self._blocks if b.date in dates]

    def add_block(self, block: TimeBlock):
        self._blocks.append(block)
        _save(CALENDAR_FILE, [b.to_dict() for b in self._blocks])

    def update_block(self, block: TimeBlock):
        for i, b in enumerate(self._blocks):
            if b.id == block.id:
                self._blocks[i] = block
                break
        _save(CALENDAR_FILE, [b.to_dict() for b in self._blocks])

    def delete_block(self, block_id: str):
        self._blocks = [b for b in self._blocks if b.id != block_id]
        _save(CALENDAR_FILE, [b.to_dict() for b in self._blocks])

    # ------------------------------------------------------------------
    # Pomodoro templates
    # ------------------------------------------------------------------

    @property
    def templates(self) -> List[PomodoroTemplate]:
        return self._templates

    def default_template(self) -> PomodoroTemplate:
        for t in self._templates:
            if t.id == self._settings.default_template_id:
                return t
        return self._templates[0]

    def save_templates(self):
        _save(TEMPLATES_FILE, [t.to_dict() for t in self._templates])

    # ------------------------------------------------------------------
    # Pomodoro sessions
    # ------------------------------------------------------------------

    @property
    def sessions(self) -> List[PomodoroSession]:
        return self._sessions

    def add_session(self, session: PomodoroSession):
        self._sessions.append(session)
        _save(POMODORO_FILE, [s.to_dict() for s in self._sessions])

    def update_session(self, session: PomodoroSession):
        for i, s in enumerate(self._sessions):
            if s.id == session.id:
                self._sessions[i] = session
                break
        _save(POMODORO_FILE, [s.to_dict() for s in self._sessions])

    # ------------------------------------------------------------------
    # Word study progress
    # ------------------------------------------------------------------

    @property
    def word_progress(self) -> dict:
        return self._word_progress

    def record_word_seen(self, word: str, correct: bool):
        entry = self._word_progress.setdefault(word, {"seen_count": 0, "correct_count": 0})
        entry["seen_count"] += 1
        if correct:
            entry["correct_count"] += 1
        _save(WORD_PROGRESS_FILE, self._word_progress)