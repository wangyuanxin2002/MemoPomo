"""
Pomodoro panel: template display, start/schedule controls,
task-selection dialog, and the controller that ties engine → calendar.
"""

import subprocess
import webbrowser
from datetime import date, datetime, timedelta

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QDialog, QDialogButtonBox,
    QComboBox, QSpinBox, QFormLayout, QLineEdit,
    QFrame, QMessageBox, QApplication,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QTime
from PyQt6.QtGui import QFont

from src.core.engine import PomodoroEngine, SegmentState
from src.core.models import (
    PomodoroSession, TimeBlock, AppSettings, MemoTask,
)
from src.core.store import Store
from src.ui.theme import PALETTE
from src.ui.word_alert import WordAlert


# ---------------------------------------------------------------------------
# Countdown dialog
# ---------------------------------------------------------------------------

class CountdownDialog(QDialog):
    """Let user choose a duration and optional task for a free countdown."""

    def __init__(self, tasks: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("自定义倒计时")
        self.setMinimumWidth(320)
        lay = QFormLayout(self)

        self._hours = QSpinBox()
        self._hours.setRange(0, 23)
        self._hours.setSuffix(" 小时")
        self._minutes = QSpinBox()
        self._minutes.setRange(0, 59)
        self._minutes.setValue(25)
        self._minutes.setSuffix(" 分钟")

        time_row = QHBoxLayout()
        time_row.addWidget(self._hours)
        time_row.addWidget(self._minutes)
        lay.addRow("倒计时时长", time_row)

        self._label_edit = QLineEdit()
        lay.addRow("计时标签（可选）", self._label_edit)

        self._combo = QComboBox()
        self._combo.addItem("不关联（自由计时）", None)
        for t in tasks:
            self._combo.addItem(f"[Q{t.quadrant}] {t.title}", t.id)
        lay.addRow("关联任务", self._combo)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addRow(btns)

    def total_seconds(self) -> int:
        return self._hours.value() * 3600 + self._minutes.value() * 60

    def label(self) -> str:
        return self._label_edit.text().strip()

    def task_id(self):
        return self._combo.currentData()


# ---------------------------------------------------------------------------
# Task-selection dialog (shown when starting a session)
# ---------------------------------------------------------------------------

class TaskSelectDialog(QDialog):
    def __init__(self, tasks: list[MemoTask], label: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("开始计时 – 关联任务")
        self.setMinimumWidth(320)
        lay = QFormLayout(self)

        self._label_edit = QLineEdit(label)
        lay.addRow("计时标签（可选）", self._label_edit)

        self._combo = QComboBox()
        self._combo.addItem("不关联（自由计时）", None)
        for t in tasks:
            self._combo.addItem(f"[Q{t.quadrant}] {t.title}", t.id)
        lay.addRow("关联任务", self._combo)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addRow(btns)

    def label(self) -> str:
        return self._label_edit.text().strip()

    def task_id(self):
        return self._combo.currentData()


# ---------------------------------------------------------------------------
# Snooze dialog
# ---------------------------------------------------------------------------

class SnoozeDialog(QDialog):
    def __init__(self, last_snooze: int = 10, parent=None):
        super().__init__(parent)
        self.setWindowTitle("是否现在开始计时？")
        self.setMinimumWidth(280)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("番茄钟计划时间到了，是否立即开始？"))

        self._start_btn = QPushButton("开始计时")
        self._start_btn.clicked.connect(self.accept)
        lay.addWidget(self._start_btn)

        snooze_row = QHBoxLayout()
        snooze_row.addWidget(QLabel("推迟"))
        self._spin = QSpinBox()
        self._spin.setRange(1, 120)
        self._spin.setValue(last_snooze)
        self._spin.setSuffix(" 分钟")
        snooze_row.addWidget(self._spin)
        snooze_btn = QPushButton("确定推迟")
        snooze_btn.clicked.connect(self.reject)   # reject = snooze
        snooze_row.addWidget(snooze_btn)
        lay.addLayout(snooze_row)

    def snooze_minutes(self) -> int:
        return self._spin.value()


# ---------------------------------------------------------------------------
# Full-screen alert window
# ---------------------------------------------------------------------------

class FullscreenAlert(QWidget):
    closed = pyqtSignal()

    def __init__(self, settings: AppSettings,
                 is_break: bool, next_label: str, parent=None):
        super().__init__(
            None,
            Qt.WindowType.Window |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.FramelessWindowHint,
        )
        # showFullScreen() alone is unreliable on some setups;
        # also set geometry to cover the full primary screen first.
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)
        self.showFullScreen()
        self.setStyleSheet(f"background:{PALETTE['accent_light']};")

        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon = QLabel("☕" if is_break else "💼")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("font-size:72px;")
        lay.addWidget(icon)

        msg = QLabel("休息时间！放松一下吧" if is_break else f"准备开始：{next_label}")
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setStyleSheet("font-size:32px; font-weight:bold;")
        lay.addWidget(msg)

        hint = QLabel("点击任意位置或按 Esc 继续")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet(f"font-size:16px; color:{PALETTE['text_sub']};")
        lay.addWidget(hint)

        # side effects: open URL / file
        if settings.alert.mode_open_url and settings.alert.url:
            webbrowser.open(settings.alert.url)
        if settings.alert.mode_open_file and settings.alert.file_path:
            subprocess.Popen(["start", "", settings.alert.file_path], shell=True)

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key.Key_Escape:
            self._close()

    def mousePressEvent(self, _):
        self._close()

    def _close(self):
        self.hide()
        self.closed.emit()


# ---------------------------------------------------------------------------
# Segment bar (visual 25+5+25+5+... strip)
# ---------------------------------------------------------------------------

class SegmentBar(QWidget):
    _ARROW_H = 8   # pixels reserved above the bar for the ▼ indicator

    def __init__(self, segments: list, parent=None):
        super().__init__(parent)
        self._segments = segments
        self._current = -1
        self.setFixedHeight(14 + self._ARROW_H)

    def set_current(self, idx: int):
        self._current = idx
        self.update()

    def paintEvent(self, _):
        from PyQt6.QtGui import QPainter, QColor, QPen, QPolygon
        from PyQt6.QtCore import QPoint
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        total = sum(s["duration_min"] for s in self._segments)
        if total == 0:
            return
        x = 0
        w = self.width()
        bar_y = self._ARROW_H      # bar starts below arrow area
        bar_h = self.height() - self._ARROW_H
        seg_centers = []
        for i, seg in enumerate(self._segments):
            seg_w = int(seg["duration_min"] / total * w)
            color = QColor(PALETTE["break_block"] if seg["is_break"]
                           else PALETTE["work_block"])
            if i != self._current:
                color = color.lighter(160)
            p.fillRect(x, bar_y, seg_w, bar_h, color)
            p.setPen(QPen(QColor("white"), 1))
            p.drawLine(x, bar_y, x, bar_y + bar_h)
            seg_centers.append(x + seg_w // 2)
            x += seg_w

        # draw ▼ arrow above the current segment
        if 0 <= self._current < len(seg_centers):
            cx = seg_centers[self._current]
            aw = 6   # half-width of triangle base
            ah = self._ARROW_H - 1
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#333333"))
            triangle = QPolygon([
                QPoint(cx - aw, 0),
                QPoint(cx + aw, 0),
                QPoint(cx, ah),
            ])
            p.drawPolygon(triangle)
        p.end()


# ---------------------------------------------------------------------------
# Pomodoro panel (main UI widget)
# ---------------------------------------------------------------------------

class PomodoroWidget(QWidget):
    """
    Shows current template, start button, and live countdown.
    Communicates with the CalendarWidget via the `session_completed` signal.
    """

    session_completed = pyqtSignal(object)   # TimeBlock

    def __init__(self, store: Store, parent=None):
        super().__init__(parent)
        self._store = store
        self._engine: PomodoroEngine | None = None
        self._session: PomodoroSession | None = None
        self._session_start: datetime | None = None
        self._alert: FullscreenAlert | None = None
        self._current_task_name: str = ""
        # countdown timer state
        self._cd_timer: QTimer | None = None
        self._cd_remaining: int = 0          # seconds left
        self._cd_start: datetime | None = None
        self._cd_label: str = ""
        self._cd_task_id = None
        self._build()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)

        # template label
        tpl_row = QHBoxLayout()
        self._tpl_lbl = QLabel()
        self._tpl_lbl.setStyleSheet(f"color:{PALETTE['text_sub']};font-size:12px;")
        tpl_row.addWidget(self._tpl_lbl, 1)
        lay.addLayout(tpl_row)

        # segment bar
        tpl = self._store.default_template()
        self._seg_bar = SegmentBar(tpl.segments)
        lay.addWidget(self._seg_bar)

        # big countdown
        self._time_lbl = QLabel("25:00")
        self._time_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = QFont()
        font.setPointSize(52)
        font.setBold(True)
        self._time_lbl.setFont(font)
        lay.addWidget(self._time_lbl)

        # status line
        self._status_lbl = QLabel('点击"开始"启动番茄钟')
        self._status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_lbl.setStyleSheet(f"color:{PALETTE['text_sub']};")
        lay.addWidget(self._status_lbl)

        # buttons
        btn_row = QHBoxLayout()
        self._start_btn = QPushButton("开始")
        self._start_btn.setFixedHeight(38)
        self._start_btn.clicked.connect(self._on_start)
        btn_row.addWidget(self._start_btn)

        self._pause_btn = QPushButton("暂停")
        self._pause_btn.setFixedHeight(38)
        self._pause_btn.setProperty("flat", True)
        self._pause_btn.setEnabled(False)
        self._pause_btn.clicked.connect(self._on_pause)
        btn_row.addWidget(self._pause_btn)

        self._reset_btn = QPushButton("重置")
        self._reset_btn.setFixedHeight(38)
        self._reset_btn.setProperty("flat", True)
        self._reset_btn.setEnabled(False)
        self._reset_btn.clicked.connect(self._on_reset)
        btn_row.addWidget(self._reset_btn)

        lay.addLayout(btn_row)

        # secondary row: countdown + word study
        sec_row = QHBoxLayout()
        cd_btn = QPushButton("自定义倒计时")
        cd_btn.setFixedHeight(34)
        cd_btn.setProperty("flat", True)
        cd_btn.clicked.connect(self._on_start_countdown)
        sec_row.addWidget(cd_btn)

        word_btn = QPushButton("开始背单词")
        word_btn.setFixedHeight(34)
        word_btn.setProperty("flat", True)
        word_btn.clicked.connect(self._on_start_words)
        sec_row.addWidget(word_btn)
        lay.addLayout(sec_row)

        self._refresh_template_label()

    def _refresh_template_label(self):
        tpl = self._store.default_template()
        parts = []
        for s in tpl.segments:
            parts.append(str(s["duration_min"]))
        self._tpl_lbl.setText(f"模板：{'+'.join(parts)}  共 {tpl.total_minutes()} 分钟")

    def refresh_template(self):
        """Called after settings dialog updates the template."""
        tpl = self._store.default_template()
        self._seg_bar._segments = tpl.segments
        self._seg_bar.update()
        self._refresh_template_label()

    # ------------------------------------------------------------------
    # Controls
    # ------------------------------------------------------------------

    def _on_start(self):
        dlg = TaskSelectDialog(self._store.memo_tasks, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        tpl = self._store.default_template()
        self._engine = PomodoroEngine(tpl.segments, self)
        self._engine.tick.connect(self._on_tick)
        self._engine.segment_finished.connect(self._on_segment_finished)
        self._engine.session_finished.connect(self._on_session_finished)

        self._session = PomodoroSession(
            template_id=tpl.id,
            memo_task_id=dlg.task_id(),
            label=dlg.label(),
            planned_date=date.today().isoformat(),
            planned_start=datetime.now().strftime("%H:%M"),
        )
        self._session_start = datetime.now()
        self._store.add_session(self._session)

        self._engine.start()
        self._start_btn.setEnabled(False)
        self._pause_btn.setEnabled(True)
        self._reset_btn.setEnabled(True)
        self._seg_bar.set_current(0)

        self._current_task_name = dlg.label() or (
            next((t.title for t in self._store.memo_tasks
                  if t.id == dlg.task_id()), "")
            if dlg.task_id() else ""
        )
        self._status_lbl.setText(
            f"正在计时：{self._current_task_name or '自由计时'}"
        )

    def _on_pause(self):
        if not self._engine:
            return
        self._engine.toggle_pause()
        self._pause_btn.setText("暂停" if self._engine.is_running else "继续")

    def _on_reset(self):
        # If a session is in progress, save it as-is (partial) before clearing
        if self._session and self._session_start and not self._session.completed:
            self._save_session_now()
        if self._engine:
            self._engine.reset()
        self._time_lbl.setText("25:00")
        self._status_lbl.setText('已重置，点击"开始"重新启动')
        self._start_btn.setEnabled(True)
        self._pause_btn.setEnabled(False)
        self._pause_btn.setText("暂停")
        self._reset_btn.setEnabled(False)
        self._seg_bar.set_current(-1)
        self._session = None
        self._session_start = None
        self._current_task_name = ""

    def _save_session_now(self):
        """Persist the current session and emit a calendar block."""
        end = datetime.now()
        self._session.actual_start = self._session_start.strftime("%H:%M")
        self._session.actual_end   = end.strftime("%H:%M")
        self._session.completed    = True
        self._store.update_session(self._session)

        task = next(
            (t for t in self._store.memo_tasks
             if t.id == self._session.memo_task_id), None
        )
        block = TimeBlock(
            title=self._session.label or (task.title if task else "番茄钟"),
            date=self._session.planned_date,
            start_time=self._session.actual_start,
            end_time=self._session.actual_end,
            memo_task_id=self._session.memo_task_id,
            is_planned=False,
            color=PALETTE["work_block"],
        )
        self.session_completed.emit(block)

    # ------------------------------------------------------------------
    # Engine callbacks
    # ------------------------------------------------------------------

    def _on_tick(self, state: SegmentState):
        self._time_lbl.setText(state.remaining_str)
        kind = "休息" if state.is_break else "专注"
        self._status_lbl.setText(
            f"{kind}  第 {state.index + 1}/{state.total} 段"
        )
        self._seg_bar.set_current(state.index)

    def _on_segment_finished(self, idx: int):
        if not self._engine:
            return
        # Don't show word alert after the last segment — session_finished will
        # fire immediately after and _on_session_finished handles cleanup.
        if idx >= len(self._engine._segments) - 1:
            return

        self._engine.pause()
        self._pause_btn.setText("继续")

        # side effects: open URL / file if configured
        settings = self._store.settings
        if settings.alert.mode_open_url and settings.alert.url:
            import webbrowser
            webbrowser.open(settings.alert.url)
        if settings.alert.mode_open_file and settings.alert.file_path:
            import subprocess
            subprocess.Popen(["start", "", settings.alert.file_path], shell=True)

        alert = WordAlert(store=self._store, standalone=False)
        def _on_alert_closed():
            if self._engine and not self._engine.is_running:
                self._engine.start()
                self._pause_btn.setText("暂停")
        alert.closed.connect(_on_alert_closed)
        alert.show()
        self._alert = alert

    def _on_start_words(self):
        alert = WordAlert(store=self._store, standalone=True)
        alert.show()
        self._alert = alert

    # ------------------------------------------------------------------
    # Custom countdown timer
    # ------------------------------------------------------------------

    def _on_start_countdown(self):
        if self._cd_timer and self._cd_timer.isActive():
            return  # already running
        dlg = CountdownDialog(self._store.memo_tasks, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        total_sec = dlg.total_seconds()
        if total_sec <= 0:
            return

        self._cd_remaining = total_sec
        self._cd_start     = datetime.now()
        self._cd_label     = dlg.label()
        self._cd_task_id   = dlg.task_id()

        self._cd_timer = QTimer(self)
        self._cd_timer.setInterval(1000)
        self._cd_timer.timeout.connect(self._cd_tick)
        self._cd_timer.start()

        # reuse status label and time label; disable pomodoro start during countdown
        self._start_btn.setEnabled(False)
        self._pause_btn.setEnabled(True)
        self._pause_btn.setText("暂停")
        self._pause_btn.clicked.disconnect()
        self._pause_btn.clicked.connect(self._cd_toggle_pause)
        self._reset_btn.setEnabled(True)
        self._reset_btn.clicked.disconnect()
        self._reset_btn.clicked.connect(self._cd_stop)

        self._status_lbl.setText(
            f"倒计时：{self._cd_label or '自由计时'}"
        )
        self._update_cd_display()

    def _cd_tick(self):
        self._cd_remaining -= 1
        self._update_cd_display()
        if self._cd_remaining <= 0:
            self._cd_timer.stop()
            self._status_lbl.setText("倒计时结束！")
            self._cd_finish()

    def _update_cd_display(self):
        h = self._cd_remaining // 3600
        m = (self._cd_remaining % 3600) // 60
        s = self._cd_remaining % 60
        if h > 0:
            self._time_lbl.setText(f"{h:02d}:{m:02d}:{s:02d}")
        else:
            self._time_lbl.setText(f"{m:02d}:{s:02d}")

    def _cd_toggle_pause(self):
        if not self._cd_timer:
            return
        if self._cd_timer.isActive():
            self._cd_timer.stop()
            self._pause_btn.setText("继续")
        else:
            self._cd_timer.start()
            self._pause_btn.setText("暂停")

    def _cd_stop(self):
        """User pressed stop/reset — save elapsed time to calendar."""
        if self._cd_timer:
            self._cd_timer.stop()
            self._cd_timer = None
        self._cd_finish()

    def _cd_finish(self):
        """Save countdown to calendar and restore UI."""
        if self._cd_start:
            end = datetime.now()
            task = next(
                (t for t in self._store.memo_tasks
                 if t.id == self._cd_task_id), None
            )
            block = TimeBlock(
                title=self._cd_label or (task.title if task else "倒计时"),
                date=self._cd_start.strftime("%Y-%m-%d"),
                start_time=self._cd_start.strftime("%H:%M"),
                end_time=end.strftime("%H:%M"),
                memo_task_id=self._cd_task_id,
                is_planned=False,
                color=PALETTE["work_block"],
            )
            self._store.add_block(block)
            self.session_completed.emit(block)

        self._cd_start   = None
        self._cd_label   = ""
        self._cd_task_id = None

        # restore normal pomodoro button wiring
        self._time_lbl.setText("25:00")
        self._status_lbl.setText('已结束，点击"开始"重新启动')
        self._start_btn.setEnabled(True)
        self._pause_btn.setEnabled(False)
        self._pause_btn.setText("暂停")
        self._pause_btn.clicked.disconnect()
        self._pause_btn.clicked.connect(self._on_pause)
        self._reset_btn.setEnabled(False)
        self._reset_btn.clicked.disconnect()
        self._reset_btn.clicked.connect(self._on_reset)

    def _on_session_finished(self):
        if not self._session or not self._session_start:
            return
        # Save immediately so the block is recorded even if the user force-quits the alert
        self._save_session_now()

        # Show word alert; reset UI only after alert is closed
        alert = WordAlert(store=self._store, standalone=False)
        alert.closed.connect(self._on_reset)
        alert.show()
        self._alert = alert

        # Disable pomodoro controls while alert is open
        self._pause_btn.setEnabled(False)
        self._pause_btn.setText("暂停")

    # ------------------------------------------------------------------
    # Public helpers (for floaty window + block alert)
    # ------------------------------------------------------------------

    def engine(self) -> PomodoroEngine | None:
        return self._engine

    def current_state(self) -> SegmentState | None:
        return self._engine.state() if self._engine else None

    @property
    def current_task_name(self) -> str:
        return self._current_task_name

    def start_for_block(self, block):
        """
        Called by the block-alert dialog to auto-start a pomodoro session
        linked to the TimeBlock's memo task (if any), without showing the
        TaskSelectDialog.
        """
        if self._engine:
            return  # already running

        tpl = self._store.default_template()
        self._engine = PomodoroEngine(tpl.segments, self)
        self._engine.tick.connect(self._on_tick)
        self._engine.segment_finished.connect(self._on_segment_finished)
        self._engine.session_finished.connect(self._on_session_finished)

        task_id = getattr(block, "memo_task_id", None)
        task = next(
            (t for t in self._store.memo_tasks if t.id == task_id), None
        ) if task_id else None

        self._session = PomodoroSession(
            template_id=tpl.id,
            memo_task_id=task_id,
            label=block.title,
            planned_date=date.today().isoformat(),
            planned_start=datetime.now().strftime("%H:%M"),
        )
        self._session_start = datetime.now()
        self._store.add_session(self._session)

        self._engine.start()
        self._start_btn.setEnabled(False)
        self._pause_btn.setEnabled(True)
        self._reset_btn.setEnabled(True)
        self._seg_bar.set_current(0)

        self._current_task_name = block.title or (task.title if task else "")
        self._status_lbl.setText(
            f"正在计时：{self._current_task_name or '自由计时'}"
        )
