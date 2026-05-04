"""
Floating mini-window: always-on-top, frameless, resizable, draggable.
- Click time digits  → open main window
- Click label area   → pause / resume
- Right-click        → context menu
- Drag bottom-right corner → resize
"""

from PyQt6.QtWidgets import QWidget, QMenu
from PyQt6.QtCore import Qt, QPoint, QRect, QTimer, pyqtSignal, QSize
from PyQt6.QtGui import QPainter, QColor, QFont, QPen

from src.ui.theme import PALETTE

_MIN_W, _MIN_H = 130, 60
_DEFAULT_W, _DEFAULT_H = 180, 80


class FloatyWindow(QWidget):
    """
    Signals:
        open_main()      – click on time digits
        toggle_pause()   – click on label area (专注/休息)
        reset_session()
        skip_segment()
        quit_app()
    """

    open_main     = pyqtSignal()
    toggle_pause  = pyqtSignal()
    reset_session = pyqtSignal()
    skip_segment  = pyqtSignal()
    quit_app      = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(
            parent,
            Qt.WindowType.Window |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(_MIN_W, _MIN_H)
        self.resize(_DEFAULT_W, _DEFAULT_H)

        self._drag_pos: QPoint | None = None
        self._resizing = False
        self._resize_start_pos: QPoint | None = None
        self._resize_start_size: QSize | None = None

        self._time_str  = "25:00"
        self._label     = "专注"
        self._task_name = ""
        self._running   = False

        # single/double click discrimination on time area
        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.setInterval(250)   # ms to wait for second click
        self._click_timer.timeout.connect(self._on_single_click_timeout)
        self._pending_click_zone: str = ""   # "time" or "label"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_state(self, time_str: str, label: str, running: bool,
                     task_name: str = ""):
        self._time_str  = time_str
        self._label     = label
        self._running   = running
        self._task_name = task_name
        self.update()

    def place(self, x: int, y: int):
        self.move(x, y)

    def save_pos(self, store):
        store.settings.floaty_pos = [self.x(), self.y()]
        store.save_settings()

    # ------------------------------------------------------------------
    # Layout helpers
    # ------------------------------------------------------------------

    def _time_rect(self) -> QRect:
        """Upper ~60% of widget – clicking opens main window."""
        return QRect(0, 0, self.width(), int(self.height() * 0.62))

    def _label_rect(self) -> QRect:
        """Lower ~38% – clicking toggles pause."""
        top = int(self.height() * 0.62)
        return QRect(0, top, self.width(), self.height() - top)

    def _resize_handle(self) -> QRect:
        """12×12 bottom-right corner for resize."""
        return QRect(self.width() - 14, self.height() - 14, 14, 14)

    # ------------------------------------------------------------------
    # Paint
    # ------------------------------------------------------------------

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # background pill
        p.setBrush(QColor(255, 255, 255, 230))
        p.setPen(QPen(QColor(PALETTE["border"]), 1))
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 12, 12)

        # time digits
        tf = QFont()
        tf.setBold(True)
        # scale font with window height
        tf.setPointSize(max(14, int(self.height() * 0.33)))
        p.setFont(tf)
        p.setPen(QPen(QColor(PALETTE["text"])))
        p.drawText(self._time_rect(),
                   Qt.AlignmentFlag.AlignCenter, self._time_str)

        # label + task name
        lf = QFont()
        lf.setPointSize(max(8, int(self.height() * 0.12)))
        p.setFont(lf)

        icon = "▶" if self._running else "⏸"
        sub = f"{icon} {self._label}"
        if self._task_name:
            sub += f"  ·  {self._task_name}"
        p.setPen(QPen(QColor(PALETTE["text_sub"])))
        p.drawText(self._label_rect().adjusted(4, 0, -4, -2),
                   Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, sub)

        # resize handle dots
        p.setPen(QPen(QColor(PALETTE["border"]), 1))
        rh = self._resize_handle()
        cx, cy = rh.center().x(), rh.center().y()
        for dx, dy in [(-3, -3), (0, -3), (3, -3),
                       (-3,  0), (0,  0), (3,  0),
                       (-3,  3), (0,  3), (3,  3)]:
            p.drawPoint(cx + dx, cy + dy)

        p.end()

    # ------------------------------------------------------------------
    # Mouse events
    # ------------------------------------------------------------------

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            pos = ev.pos()
            if self._resize_handle().contains(pos):
                self._resizing = True
                self._resize_start_pos  = ev.globalPosition().toPoint()
                self._resize_start_size = self.size()
            else:
                self._drag_pos = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, ev):
        pos = ev.pos()
        if self._resizing and self._resize_start_pos and self._resize_start_size:
            delta = ev.globalPosition().toPoint() - self._resize_start_pos
            new_w = max(_MIN_W, self._resize_start_size.width()  + delta.x())
            new_h = max(_MIN_H, self._resize_start_size.height() + delta.y())
            self.resize(new_w, new_h)
        elif (ev.buttons() & Qt.MouseButton.LeftButton) and self._drag_pos:
            self.move(ev.globalPosition().toPoint() - self._drag_pos)
        # cursor hint
        if self._resize_handle().contains(pos):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            if self._resizing:
                self._resizing = False
                self._resize_start_pos  = None
                self._resize_start_size = None
                return
            if self._drag_pos:
                drag_dist = (
                    ev.globalPosition().toPoint()
                    - self.frameGeometry().topLeft()
                    - self._drag_pos
                ).manhattanLength()
                self._drag_pos = None
                if drag_dist > 6:
                    return  # was a drag, not a click

            # determine which zone was clicked – start timer to detect double-click
            pos = ev.pos()
            if self._time_rect().contains(pos):
                self._pending_click_zone = "time"
                self._click_timer.start()
            elif self._label_rect().contains(pos):
                self._pending_click_zone = "label"
                self._click_timer.start()

    def mouseDoubleClickEvent(self, ev):
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        self._click_timer.stop()
        self._pending_click_zone = ""
        pos = ev.pos()
        if self._time_rect().contains(pos):
            self.open_main.emit()
        elif self._label_rect().contains(pos):
            self.toggle_pause.emit()

    def _on_single_click_timeout(self):
        # single click confirmed – only label zone does something
        if self._pending_click_zone == "label":
            self.toggle_pause.emit()
        # time zone: single click = no-op
        self._pending_click_zone = ""

    def contextMenuEvent(self, ev):
        menu = QMenu(self)
        menu.addAction("展开主界面").triggered.connect(self.open_main.emit)
        menu.addSeparator()
        menu.addAction("暂停 / 继续").triggered.connect(self.toggle_pause.emit)
        menu.addAction("跳过本段").triggered.connect(self.skip_segment.emit)
        menu.addAction("放弃 / 重置").triggered.connect(self.reset_session.emit)
        menu.addSeparator()
        menu.addAction("退出程序").triggered.connect(self.quit_app.emit)
        menu.exec(ev.globalPos())
