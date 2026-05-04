"""
Pomodoro timer engine – pure logic, no UI dependency.
Emits signals via callbacks so the UI can stay decoupled.
"""

from dataclasses import dataclass
from typing import Callable, List, Optional
from PyQt6.QtCore import QTimer, QObject, pyqtSignal


@dataclass
class SegmentState:
    index: int
    total: int
    duration_min: int
    elapsed_sec: int
    is_break: bool

    @property
    def remaining_sec(self) -> int:
        return self.duration_min * 60 - self.elapsed_sec

    @property
    def remaining_str(self) -> str:
        r = max(0, self.remaining_sec)
        return f"{r // 60:02d}:{r % 60:02d}"


class PomodoroEngine(QObject):
    """
    Drives the pomodoro sequence.

    Signals:
        tick(SegmentState)        – fires every second while running
        segment_finished(int)     – segment index that just ended
        session_finished()        – all segments done
    """

    tick = pyqtSignal(object)
    segment_finished = pyqtSignal(int)
    session_finished = pyqtSignal()

    def __init__(self, segments: list, parent=None):
        """
        segments: list of dicts {"duration_min": int, "is_break": bool}
        """
        super().__init__(parent)
        self._segments = segments
        self._current = 0
        self._elapsed = 0
        self._running = False

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._on_tick)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self):
        if not self._running:
            self._running = True
            self._timer.start()

    def pause(self):
        if self._running:
            self._running = False
            self._timer.stop()

    def toggle_pause(self):
        if self._running:
            self.pause()
        else:
            self.start()

    def reset(self):
        self._timer.stop()
        self._running = False
        self._current = 0
        self._elapsed = 0

    def skip_segment(self):
        """Immediately advance to the next segment."""
        self._advance()

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_paused(self) -> bool:
        return not self._running and self._current < len(self._segments)

    def state(self) -> SegmentState:
        idx = min(self._current, len(self._segments) - 1)
        seg = self._segments[idx]
        return SegmentState(
            index=idx,
            total=len(self._segments),
            duration_min=seg["duration_min"],
            elapsed_sec=self._elapsed,
            is_break=seg["is_break"],
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_tick(self):
        self._elapsed += 1
        seg = self._segments[self._current]
        self.tick.emit(self.state())

        if self._elapsed >= seg["duration_min"] * 60:
            self._advance()

    def _advance(self):
        finished_idx = self._current
        self._elapsed = 0
        self._current += 1
        self.segment_finished.emit(finished_idx)

        if self._current >= len(self._segments):
            self._timer.stop()
            self._running = False
            self.session_finished.emit()
