"""
Main window: left = calendar + pomodoro, right = memo four-quadrant.
"""

from datetime import date as _date, datetime
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QLabel, QDialog, QVBoxLayout as QVBox,
    QHBoxLayout as QHBox, QSpinBox, QApplication,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QCloseEvent, QFont

from src.core.models import TimeBlock
from src.core.store import Store
from src.ui.calendar_widget import CalendarWidget
from src.ui.memo_widget import MemoWidget
from src.ui.pomodoro_widget import PomodoroWidget
from src.ui.floaty_window import FloatyWindow
from src.ui.settings_dialog import SettingsDialog
from src.ui.sticky_window import StickyWindow
from src.ui.theme import PALETTE


# ---------------------------------------------------------------------------
# Block-start alert dialog
# ---------------------------------------------------------------------------

class BlockAlertDialog(QDialog):
    """
    Fullscreen-style alert when a TimeBlock's start_time is reached.
    Options: 启动任务 (accept) | 推迟 N 分钟 (reject).
    """

    def __init__(self, block: TimeBlock, default_snooze: int, parent=None):
        super().__init__(
            None,
            Qt.WindowType.Window |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.FramelessWindowHint,
        )
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)
        self.showFullScreen()
        self.setStyleSheet(f"background:{PALETTE['accent_light']};")

        self._snoozed_minutes = default_snooze

        root = QVBoxLayout(self)
        root.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.setSpacing(24)
        root.setContentsMargins(120, 80, 120, 80)

        # icon
        icon = QLabel("🗓")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("font-size:72px;")
        root.addWidget(icon)

        # task name
        title_lbl = QLabel(f'「{block.title}」')
        f = QFont()
        f.setPointSize(28)
        f.setBold(True)
        title_lbl.setFont(f)
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(title_lbl)

        # start time + duration
        try:
            sh, sm = map(int, block.start_time.split(":"))
            eh, em = map(int, block.end_time.split(":"))
            dur = (eh * 60 + em) - (sh * 60 + sm)
            info = f"开始时间 {block.start_time}，计划时长 {dur} 分钟"
        except Exception:
            info = f"开始时间 {block.start_time}"
        info_lbl = QLabel(info)
        info_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_lbl.setStyleSheet(f"font-size:18px; color:{PALETTE['text_sub']};")
        root.addWidget(info_lbl)

        root.addSpacing(20)

        # start button
        start_btn = QPushButton("🚀  启动任务")
        start_btn.setFixedHeight(52)
        start_btn.setStyleSheet(
            f"background:{PALETTE['accent']}; color:white; font-size:18px;"
            "border:none; border-radius:10px; padding:0 40px;"
        )
        start_btn.clicked.connect(self.accept)
        root.addWidget(start_btn)

        # snooze row
        snooze_row = QHBoxLayout()
        snooze_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        snooze_lbl = QLabel("推迟")
        snooze_lbl.setStyleSheet("font-size:16px;")
        snooze_row.addWidget(snooze_lbl)

        self._snooze_spin = QSpinBox()
        self._snooze_spin.setRange(1, 120)
        self._snooze_spin.setValue(default_snooze)
        self._snooze_spin.setSuffix(" 分钟")
        self._snooze_spin.setFixedHeight(40)
        self._snooze_spin.setStyleSheet(
            "font-size:16px; background:white; border:1px solid #ccc; border-radius:6px; padding:2px 8px;"
        )
        snooze_row.addWidget(self._snooze_spin)

        snooze_btn = QPushButton("推迟")
        snooze_btn.setFixedHeight(40)
        snooze_btn.setStyleSheet(
            f"background:{PALETTE['surface2']}; color:{PALETTE['text']};"
            "font-size:16px; border:1px solid #bbb; border-radius:8px; padding:0 24px;"
        )
        snooze_btn.clicked.connect(self._do_snooze)
        snooze_row.addWidget(snooze_btn)
        root.addLayout(snooze_row)

    def _do_snooze(self):
        self._snoozed_minutes = self._snooze_spin.value()
        self.reject()

    def snooze_minutes(self) -> int:
        return self._snoozed_minutes


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self, store: Store):
        super().__init__()
        self._store = store
        self.setWindowTitle("MemoPomo | 备忘番茄")
        self.resize(1200, 750)
        # track which block_ids have already been alerted this session
        self._alerted_blocks: set[str] = set()
        # track snoozed blocks: block_id → datetime when to re-alert
        self._snoozed: dict[str, datetime] = {}

        self._sticky_win: StickyWindow | None = None
        self._build()
        self._setup_floaty()
        self._setup_reminder_poll()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # ---- Left pane: pomodoro + calendar ----
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(8)

        # top bar
        top_bar = QHBoxLayout()
        _weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        _today = _date.today()
        _date_str = f"{_today.year}年{_today.month}月{_today.day}日  {_weekdays[_today.weekday()]}"
        date_lbl = QLabel(_date_str)
        date_lbl.setStyleSheet("font-size:14px; font-weight:bold;")
        top_bar.addWidget(date_lbl, 1)
        settings_btn = QPushButton("⚙ 设置")
        settings_btn.setProperty("flat", True)
        settings_btn.clicked.connect(self._open_settings)
        top_bar.addWidget(settings_btn)
        minimize_btn = QPushButton("最小化到悬浮窗")
        minimize_btn.setProperty("flat", True)
        minimize_btn.clicked.connect(self._minimize_to_floaty)
        top_bar.addWidget(minimize_btn)
        left_lay.addLayout(top_bar)

        # pomodoro widget (compact height)
        self._pomo = PomodoroWidget(self._store)
        self._pomo.setMaximumHeight(280)
        self._pomo.session_completed.connect(self._on_session_completed)
        left_lay.addWidget(self._pomo)

        # calendar
        self._cal = CalendarWidget(self._store)
        left_lay.addWidget(self._cal, 1)

        root.addWidget(left, 9)

        # ---- Right pane: memo ----
        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)

        title_row = QHBoxLayout()
        memo_title = QLabel("备忘录 · 四象限")
        memo_title.setStyleSheet("font-size:14px; font-weight:bold;")
        title_row.addWidget(memo_title, 1)
        sticky_btn = QPushButton("便利贴")
        sticky_btn.setProperty("flat", True)
        sticky_btn.clicked.connect(self._open_sticky)
        title_row.addWidget(sticky_btn)
        right_lay.addLayout(title_row)

        self._memo = MemoWidget(self._store)
        right_lay.addWidget(self._memo, 1)

        root.addWidget(right, 11)

        # status bar
        self.statusBar().showMessage("就绪")

    # ------------------------------------------------------------------
    # Block reminder polling
    # ------------------------------------------------------------------

    def _setup_reminder_poll(self):
        self._reminder_timer = QTimer(self)
        self._reminder_timer.setInterval(30_000)   # check every 30 s
        self._reminder_timer.timeout.connect(self._check_block_reminders)
        self._reminder_timer.start()
        # also check immediately on startup
        QTimer.singleShot(2000, self._check_block_reminders)

    def _check_block_reminders(self):
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")
        current_hm = now.strftime("%H:%M")

        for block in list(self._store.time_blocks):
            if block.date != today_str:
                continue
            if block.start_time != current_hm:
                continue
            if block.id in self._alerted_blocks:
                continue
            # check snooze
            if block.id in self._snoozed:
                if now < self._snoozed[block.id]:
                    continue
                del self._snoozed[block.id]

            self._alerted_blocks.add(block.id)
            self._show_block_alert(block)
            break   # show one alert at a time; next will fire on next tick

    def _show_block_alert(self, block: TimeBlock):
        default_snooze = self._store.settings.snooze_minutes
        dlg = BlockAlertDialog(block, default_snooze)
        result = dlg.exec()

        if result == QDialog.DialogCode.Accepted:
            # Update default snooze value
            self._store.settings.snooze_minutes = dlg.snooze_minutes()
            # Start pomodoro with this task
            self._show_main()
            self._pomo.start_for_block(block)
            self._start_floaty_updates()
        else:
            # Snoozed: re-alert after chosen minutes
            snooze_min = dlg.snooze_minutes()
            self._store.settings.snooze_minutes = snooze_min
            self._store.save_settings()
            from datetime import timedelta
            self._snoozed[block.id] = datetime.now() + timedelta(minutes=snooze_min)
            # allow re-alert after snooze
            self._alerted_blocks.discard(block.id)

    # ------------------------------------------------------------------
    # Floaty window
    # ------------------------------------------------------------------

    def _setup_floaty(self):
        self._floaty = FloatyWindow()
        pos = self._store.settings.floaty_pos
        self._floaty.place(*pos)

        self._floaty.open_main.connect(self._show_main)
        self._floaty.toggle_pause.connect(self._on_floaty_toggle_pause)
        self._floaty.reset_session.connect(self._pomo._on_reset)
        self._floaty.skip_segment.connect(self._on_skip_segment)
        self._floaty.quit_app.connect(self._quit)

        self._pomo._start_btn.clicked.connect(self._start_floaty_updates)

    def _start_floaty_updates(self):
        engine = self._pomo.engine()
        if engine:
            engine.tick.connect(self._on_engine_tick)

    def _on_engine_tick(self, state):
        kind = "休息" if state.is_break else "专注"
        engine = self._pomo.engine()
        running = engine.is_running if engine else False
        self._floaty.update_state(
            state.remaining_str, kind, running,
            task_name=self._pomo.current_task_name,
        )

    def _minimize_to_floaty(self):
        self.hide()
        self._floaty.show()

    def _show_main(self):
        self.show()
        self.activateWindow()
        self._floaty.hide()

    def _on_floaty_toggle_pause(self):
        engine = self._pomo.engine()
        if engine:
            engine.toggle_pause()
            state = engine.state()
            kind = "休息" if state.is_break else "专注"
            self._floaty.update_state(state.remaining_str, kind, engine.is_running)

    def _on_floaty_click(self):
        pass

    def _on_skip_segment(self):
        engine = self._pomo.engine()
        if engine:
            engine.skip_segment()

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def _on_session_completed(self, block):
        self._cal.add_block_from_session(block)
        self.statusBar().showMessage(
            f"番茄钟完成：{block.title}  {block.start_time}–{block.end_time}", 5000
        )

    def _open_sticky(self):
        if self._sticky_win is None or not self._sticky_win.isVisible():
            self._sticky_win = StickyWindow(self._store)
        self._sticky_win.show()
        self._sticky_win.raise_()
        self._sticky_win.activateWindow()

    def _open_settings(self):
        dlg = SettingsDialog(self._store, self)
        if dlg.exec():
            self._pomo.refresh_template()
            self._memo.refresh()
            self._cal.refresh()

    def _quit(self):
        self._floaty.save_pos(self._store)
        QApplication.quit()

    def closeEvent(self, ev: QCloseEvent):
        self._floaty.save_pos(self._store)
        ev.accept()
