"""
Calendar widget with three views: Week / Day / Month.

Week & Day views:
  - Time axis grid, blocks rendered as colored rects
  - Block text: "HH:MM  Xm  标题"  (start time + duration in minutes + title)
  - Left-click on block → edit/delete dialog
  - Drag block body → move to new day/time (week view) or new time (day view)
  - Drag block bottom edge → resize (change end time / duration)
  - Drop from MemoWidget → create 1-hour planned block

Month view:
  - Grid of weeks, each cell lists block titles for that day

Block color: if the block is linked to a memo task, use the quadrant color;
             otherwise use the block's own color field.
"""

from datetime import date, timedelta, datetime, time as dtime
from calendar import monthcalendar
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QFrame, QDialog,
    QDialogButtonBox, QLineEdit, QFormLayout,
    QComboBox, QStackedWidget, QGridLayout, QSizePolicy,
    QSpinBox,
)
from PyQt6.QtCore import Qt, pyqtSignal, QRect, QPoint, QMimeData, QSize, QTimer
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QDrag, QFont

from src.core.models import TimeBlock, MemoTask
from src.core.store import Store
from src.ui.theme import PALETTE
from src.ui.memo_widget import MIME_TYPE

# ── grid constants ──────────────────────────────────────────────────────────
HOUR_H  = 64     # pixels per hour (default; overridden by store settings)
DAY_W   = 120    # pixels per day column (week view)
TIME_W  = 50     # left time-label column
START_H = 0      # default start hour
END_H   = 24     # default end hour

WEEK_HEADERS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

# quadrant → block colour
_Q_COLOR = {
    1: PALETTE["q1_header"],
    2: PALETTE["q2_header"],
    3: PALETTE["q3_header"],
    4: PALETTE["q4_header"],
}

BLOCK_MIME = "application/x-calblock-id"


# ── helpers ──────────────────────────────────────────────────────────────────

def _hm_to_y(hm: str, hour_h: int = HOUR_H, start_h: int = START_H) -> float:
    h, m = map(int, hm.split(":"))
    return (h - start_h) * hour_h + m * hour_h / 60


def _y_to_hm(y: float, snap: bool = False,
             hour_h: int = HOUR_H, start_h: int = START_H) -> str:
    total_min = int(y * 60 / hour_h) + start_h * 60
    if snap:
        total_min = round(total_min / 15) * 15
    total_min = max(0, min(23 * 60 + 59, total_min))
    return f"{total_min // 60:02d}:{total_min % 60:02d}"


def _duration_min(start: str, end: str) -> int:
    sh, sm = map(int, start.split(":"))
    eh, em = map(int, end.split(":"))
    return max(0, (eh * 60 + em) - (sh * 60 + sm))


def _add_min(hm: str, minutes: int) -> str:
    h, m = map(int, hm.split(":"))
    total = h * 60 + m + minutes
    total = max(0, min(23 * 60 + 59, total))
    return f"{total // 60:02d}:{total % 60:02d}"


def _week_dates(ref: date) -> list[date]:
    mon = ref - timedelta(days=ref.weekday())
    return [mon + timedelta(days=i) for i in range(7)]


def _block_color(block: TimeBlock, store: Store) -> QColor:
    """Return display colour: quadrant colour if task linked, else block colour."""
    if block.memo_task_id:
        task = next(
            (t for t in store.memo_tasks if t.id == block.memo_task_id), None
        )
        if task:
            # use user-customised quadrant colour if available
            q_colors = getattr(store.settings, "quadrant_colors", None)
            if q_colors and len(q_colors) >= 4:
                return QColor(q_colors[task.quadrant - 1])
            return QColor(_Q_COLOR[task.quadrant])
    if block.is_planned:
        return QColor(PALETTE["plan_block"])
    return QColor(block.color or PALETTE["work_block"])


def _block_label(block: TimeBlock) -> str:
    dur = _duration_min(block.start_time, block.end_time)
    parts = [block.start_time, f"{dur}m"]
    if block.title:
        parts.append(block.title)
    return "  ".join(parts)


# ── BlockItem ────────────────────────────────────────────────────────────────

class BlockItem:
    def __init__(self, block: TimeBlock, col: int, day_w: int = DAY_W,
                 hour_h: int = HOUR_H, start_h: int = START_H):
        self.block   = block
        self.col     = col
        self._day_w  = day_w
        self._hour_h = hour_h
        self._start_h = start_h

    def rect(self) -> QRect:
        x = TIME_W + self.col * self._day_w + 2
        y = int(_hm_to_y(self.block.start_time, self._hour_h, self._start_h))
        h = max(16, int(_hm_to_y(self.block.end_time, self._hour_h, self._start_h)) - y)
        return QRect(x, y, self._day_w - 4, h)

    def resize_handle(self) -> QRect:
        r = self.rect()
        return QRect(r.left(), r.bottom() - 8, r.width(), 8)


# ── Dialogs ──────────────────────────────────────────────────────────────────

class _SnapMinuteSpinBox(QSpinBox):
    """Minutes spinbox: step snaps to next/prev 15-min boundary first."""
    def stepBy(self, steps: int):
        v = self.value()
        if steps > 0:
            # snap up to next 15-min boundary, then continue in 15-min steps
            snapped = (v // 15 + 1) * 15
            if snapped == v + 15:
                # already on a boundary — just add 15
                self.setValue(min(self.maximum(), v + 15))
            else:
                self.setValue(min(self.maximum(), snapped))
        else:
            # snap down to previous 15-min boundary
            if v % 15 == 0:
                self.setValue(max(self.minimum(), v - 15))
            else:
                self.setValue((v // 15) * 15)


class BlockEditDialog(QDialog):
    def __init__(self, block: TimeBlock, tasks: list[MemoTask], parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑时间块")
        self.setMinimumWidth(300)
        self._block   = block
        self._deleted = False

        form = QFormLayout(self)

        self._title = QLineEdit(block.title)
        form.addRow("标题", self._title)

        sh, sm = map(int, block.start_time.split(":"))
        self._start_h = QSpinBox()
        self._start_h.setRange(0, 23)
        self._start_h.setValue(sh)
        self._start_h.setSuffix(" 时")
        self._start_m = _SnapMinuteSpinBox()
        self._start_m.setRange(0, 59)
        self._start_m.setValue(sm)
        self._start_m.setSuffix(" 分")
        start_row = QHBoxLayout()
        start_row.addWidget(self._start_h)
        start_row.addWidget(self._start_m)
        form.addRow("开始", start_row)

        raw_dur = _duration_min(block.start_time, block.end_time)
        snapped_dur = max(15, round(raw_dur / 15) * 15)
        self._dur = QSpinBox()
        self._dur.setRange(15, 23 * 60)
        self._dur.setSingleStep(15)
        self._dur.setSuffix(" 分钟")
        self._dur.setValue(snapped_dur)
        form.addRow("持续时间", self._dur)

        self._task_combo = QComboBox()
        self._task_combo.addItem("（无关联任务）", None)
        for t in tasks:
            self._task_combo.addItem(f"[Q{t.quadrant}] {t.title}", t.id)
            if t.id == block.memo_task_id:
                self._task_combo.setCurrentIndex(self._task_combo.count() - 1)
        form.addRow("关联任务", self._task_combo)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel |
            QDialogButtonBox.StandardButton.Discard,
        )
        btns.button(QDialogButtonBox.StandardButton.Discard).setText("删除")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        btns.button(QDialogButtonBox.StandardButton.Discard).clicked.connect(
            self._on_delete)
        form.addRow(btns)

    def _on_delete(self):
        self._deleted = True
        self.done(QDialog.DialogCode.Accepted)

    def is_deleted(self) -> bool:
        return self._deleted

    def apply_to(self, block: TimeBlock):
        block.title        = self._title.text().strip()
        block.start_time   = f"{self._start_h.value():02d}:{self._start_m.value():02d}"
        block.end_time     = _add_min(block.start_time, self._dur.value())
        block.memo_task_id = self._task_combo.currentData()


class NewBlockDialog(QDialog):
    def __init__(self, date_str: str, hm_str: str,
                 tasks: list[MemoTask], parent=None):
        super().__init__(parent)
        self.setWindowTitle("新建时间块")
        self.setMinimumWidth(300)
        self._date_str = date_str

        form = QFormLayout(self)

        self._title = QLineEdit()
        form.addRow("标题", self._title)

        # snap hm_str to nearest 15-minute mark
        _h, _m = map(int, hm_str.split(":"))
        _snapped_m = round((_h * 60 + _m) / 15) * 15
        _snapped_h, _snapped_min = divmod(_snapped_m, 60)
        _snapped_h = min(_snapped_h, 23)

        self._start_h = QSpinBox()
        self._start_h.setRange(0, 23)
        self._start_h.setValue(_snapped_h)
        self._start_h.setSuffix(" 时")
        self._start_m = QSpinBox()
        self._start_m.setRange(0, 45)
        self._start_m.setValue(_snapped_min)
        self._start_m.setSingleStep(15)
        self._start_m.setSuffix(" 分")
        start_row = QHBoxLayout()
        start_row.addWidget(self._start_h)
        start_row.addWidget(self._start_m)
        form.addRow("开始", start_row)

        self._dur = QSpinBox()
        self._dur.setRange(15, 23 * 60)
        self._dur.setValue(60)
        self._dur.setSingleStep(15)
        self._dur.setSuffix(" 分钟")
        form.addRow("持续时间", self._dur)

        self._task_combo = QComboBox()
        self._task_combo.addItem("（无关联任务）", None)
        for t in tasks:
            self._task_combo.addItem(f"[Q{t.quadrant}] {t.title}", t.id)
        form.addRow("关联任务", self._task_combo)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def build_block(self) -> TimeBlock:
        task_id    = self._task_combo.currentData()
        task_title = (self._task_combo.currentText()
                      if self._task_combo.currentIndex() > 0 else "")
        title      = self._title.text().strip() or task_title
        start      = f"{self._start_h.value():02d}:{self._start_m.value():02d}"
        end        = _add_min(start, self._dur.value())
        return TimeBlock(
            title=title, date=self._date_str,
            start_time=start, end_time=end,
            memo_task_id=task_id, is_planned=False,
        )


# ── TimeGrid (shared by Week and Day views) ──────────────────────────────────

class TimeGrid(QWidget):
    """
    Raw paintable grid.  Handles:
      - drawing hour lines, column separators, block rects
      - left-click on block (no drag)  → block_clicked
      - drag block body                → block_moved(id, new_date_str, new_hm)
      - drag block bottom edge         → block_resized(id, new_end_hm)
      - left-click on empty area       → empty_clicked(date_str, hm)
      - drop from MemoWidget           → memo_dropped(task_id, date_str, hm)
    """

    block_clicked  = pyqtSignal(object)          # BlockItem
    block_moved    = pyqtSignal(str, str, str)   # block_id, date_str, hm
    block_resized  = pyqtSignal(str, str)         # block_id, new_end_hm
    empty_clicked  = pyqtSignal(str, str)         # date_str, hm
    memo_dropped   = pyqtSignal(str, str, str)    # task_id, date_str, hm

    def __init__(self, dates: list[date], store: Store,
                 day_w: int = DAY_W, parent=None,
                 hour_h: int = HOUR_H, start_h: int = START_H, end_h: int = END_H):
        super().__init__(parent)
        self._dates   = dates
        self._store   = store
        self._day_w   = day_w
        self._hour_h  = hour_h
        self._start_h = start_h
        self._end_h   = end_h
        self._items: list[BlockItem] = []

        self._press_pos:   QPoint | None   = None
        self._active_item: BlockItem | None = None
        self._resize_item: BlockItem | None = None
        self._drag_offset: QPoint = QPoint(0, 0)
        self._ghost_rect:  QRect | None    = None  # visual while dragging

        self.setAcceptDrops(True)
        total_h = (end_h - start_h) * hour_h
        self.setFixedSize(TIME_W + day_w * len(dates), total_h)

    def set_items(self, items: list[BlockItem]):
        self._items = items
        self.update()

    # ── paint ──────────────────────────────────────────────────────────

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        total_h = (self._end_h - self._start_h) * self._hour_h
        total_w = TIME_W + self._day_w * len(self._dates)

        p.fillRect(0, 0, total_w, total_h, QColor(PALETTE["surface"]))

        # hour grid lines + labels
        pen = QPen(QColor(PALETTE["border"]), 1)
        p.setPen(pen)
        for h in range(self._start_h, self._end_h + 1):
            y = (h - self._start_h) * self._hour_h
            p.drawLine(TIME_W, y, total_w, y)
            if h < self._end_h:
                p.drawText(0, y + 2, TIME_W - 4, 20,
                           Qt.AlignmentFlag.AlignRight, f"{h:02d}:00")

        # column separators
        for c in range(len(self._dates) + 1):
            x = TIME_W + c * self._day_w
            p.drawLine(x, 0, x, total_h)

        # today highlight
        today = date.today()
        if today in self._dates:
            col = self._dates.index(today)
            x = TIME_W + col * self._day_w
            p.fillRect(x + 1, 0, self._day_w - 1, total_h,
                       QColor(PALETTE["accent_light"]))

        # blocks
        for item in self._items:
            is_ghost = (self._active_item is item
                        and self._ghost_rect is not None)
            r = self._ghost_rect if is_ghost else item.rect()
            c = _block_color(item.block, self._store)
            p.setBrush(QBrush(c))
            p.setPen(QPen(c.darker(140), 1))
            p.drawRoundedRect(r, 4, 4)

            # resize handle bar
            p.fillRect(r.left(), r.bottom() - 6, r.width(), 6,
                       c.darker(160))

            # label
            lf = QFont()
            lf.setPointSize(8)
            p.setFont(lf)
            p.setPen(QPen(QColor("#1A1A1A")))
            p.drawText(r.adjusted(3, 2, -3, -8),
                       Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
                       _block_label(item.block))

        p.end()

    # ── mouse ──────────────────────────────────────────────────────────

    def mousePressEvent(self, ev):
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        pos = ev.pos()
        self._press_pos   = pos
        self._active_item = None
        self._resize_item = None
        self._ghost_rect  = None

        for item in reversed(self._items):
            if item.resize_handle().contains(pos):
                self._resize_item = item
                return
            if item.rect().contains(pos):
                self._active_item = item
                self._drag_offset = pos - item.rect().topLeft()
                return

    def mouseMoveEvent(self, ev):
        if not (ev.buttons() & Qt.MouseButton.LeftButton):
            return
        pos = ev.pos()

        if self._resize_item:
            start_y = _hm_to_y(self._resize_item.block.start_time,
                                self._hour_h, self._start_h) + 5
            if pos.y() > start_y:
                snapped_end = _y_to_hm(pos.y(), snap=True,
                                        hour_h=self._hour_h, start_h=self._start_h)
                snapped_y   = int(_hm_to_y(snapped_end, self._hour_h, self._start_h))
                r = self._resize_item.rect()
                self._ghost_rect = QRect(r.left(), r.top(),
                                         r.width(), snapped_y - r.top())
                self.update()
            return

        if self._active_item and self._press_pos:
            if (pos - self._press_pos).manhattanLength() < 6:
                return
            # compute ghost position with snap
            raw_top_y   = pos.y() - self._drag_offset.y()
            snapped_hm  = _y_to_hm(raw_top_y, snap=True,
                                    hour_h=self._hour_h, start_h=self._start_h)
            snapped_y   = int(_hm_to_y(snapped_hm, self._hour_h, self._start_h))
            col         = (pos.x() - TIME_W) // self._day_w
            col         = max(0, min(len(self._dates) - 1, col))
            r           = self._active_item.rect()
            self._ghost_rect = QRect(
                TIME_W + col * self._day_w + 2, snapped_y,
                self._day_w - 4, r.height()
            )
            self.update()

    def mouseReleaseEvent(self, ev):
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        pos = ev.pos()

        if self._resize_item:
            new_end = _y_to_hm(
                max(_hm_to_y(self._resize_item.block.start_time,
                              self._hour_h, self._start_h) + 5,
                    float(pos.y())),
                snap=True, hour_h=self._hour_h, start_h=self._start_h,
            )
            self.block_resized.emit(self._resize_item.block.id, new_end)
            self._resize_item = None
            self._ghost_rect  = None
            self.update()
            return

        if self._active_item:
            moved = (self._press_pos is not None and
                     (pos - self._press_pos).manhattanLength() >= 6)
            if moved and self._ghost_rect:
                col = (pos.x() - TIME_W) // self._day_w
                col = max(0, min(len(self._dates) - 1, col))
                new_date = self._dates[col].isoformat()
                new_hm   = _y_to_hm(self._ghost_rect.top(), snap=True,
                                     hour_h=self._hour_h, start_h=self._start_h)
                self.block_moved.emit(
                    self._active_item.block.id, new_date, new_hm)
            else:
                self.block_clicked.emit(self._active_item)

            self._active_item = None
            self._ghost_rect  = None
            self._press_pos   = None
            self.update()
            return

        # click on empty area
        col = (pos.x() - TIME_W) // self._day_w
        if 0 <= col < len(self._dates):
            self.empty_clicked.emit(self._dates[col].isoformat(),
                                    _y_to_hm(pos.y(), hour_h=self._hour_h,
                                              start_h=self._start_h))

    # ── drops from MemoWidget ─────────────────────────────────────────

    def dragEnterEvent(self, ev):
        if ev.mimeData().hasFormat(MIME_TYPE):
            ev.acceptProposedAction()

    def dragMoveEvent(self, ev):
        ev.acceptProposedAction()

    def dropEvent(self, ev):
        task_id = ev.mimeData().data(MIME_TYPE).data().decode()
        pos = ev.position().toPoint()
        col = (pos.x() - TIME_W) // self._day_w
        if 0 <= col < len(self._dates):
            self.memo_dropped.emit(task_id,
                                   self._dates[col].isoformat(),
                                   _y_to_hm(pos.y(), hour_h=self._hour_h,
                                             start_h=self._start_h))
        ev.acceptProposedAction()


# ── Month view ────────────────────────────────────────────────────────────────

class MonthView(QWidget):
    def __init__(self, store: Store, parent=None):
        super().__init__(parent)
        self._store    = store
        self._ref_date = date.today()
        self._build()
        self.refresh()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        # day-of-week header
        hdr = QHBoxLayout()
        hdr.setSpacing(0)
        for h in WEEK_HEADERS:
            lbl = QLabel(h)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(f"font-weight:bold;background:{PALETTE['surface2']};")
            hdr.addWidget(lbl, 1)
        root.addLayout(hdr)

        self._grid = QGridLayout()
        self._grid.setSpacing(2)
        root.addLayout(self._grid, 1)

    def _prev(self):
        d = self._ref_date.replace(day=1) - timedelta(days=1)
        self._ref_date = d.replace(day=1)
        self.refresh()

    def _next(self):
        d = self._ref_date.replace(day=28) + timedelta(days=4)
        self._ref_date = d.replace(day=1)
        self.refresh()

    def _this(self):
        self._ref_date = date.today()
        self.refresh()

    def refresh(self):
        # clear grid
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        weeks = monthcalendar(self._ref_date.year, self._ref_date.month)
        today = date.today()

        # collect all blocks for this month
        all_dates = [
            date(self._ref_date.year, self._ref_date.month, d)
            for w in weeks for d in w if d != 0
        ]
        date_strs = [d.isoformat() for d in all_dates]
        blocks_by_date: dict[str, list[TimeBlock]] = {}
        for b in self._store.time_blocks:
            if b.date in date_strs:
                blocks_by_date.setdefault(b.date, []).append(b)

        for row, week in enumerate(weeks):
            for col, day in enumerate(week):
                cell = QFrame()
                cell.setFrameShape(QFrame.Shape.StyledPanel)
                cell_lay = QVBoxLayout(cell)
                cell_lay.setContentsMargins(2, 2, 2, 2)
                cell_lay.setSpacing(1)

                if day == 0:
                    cell.setStyleSheet(f"background:{PALETTE['surface2']};")
                    self._grid.addWidget(cell, row, col)
                    continue

                d = date(self._ref_date.year, self._ref_date.month, day)
                is_today = (d == today)
                num_lbl = QLabel(str(day))
                num_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
                num_lbl.setStyleSheet(
                    "font-weight:bold;color:white;"
                    f"background:{PALETTE['accent']}; border-radius:10px;"
                    "padding:1px 4px;" if is_today else
                    f"color:{PALETTE['text']};"
                )
                cell_lay.addWidget(num_lbl)

                for b in blocks_by_date.get(d.isoformat(), [])[:3]:
                    c = _block_color(b, self._store)
                    tag = QLabel(f"{b.start_time} {b.title or '—'}")
                    tag.setStyleSheet(
                        f"background:{c.name()}; border-radius:2px;"
                        "font-size:10px; padding:1px 3px;"
                    )
                    tag.setMaximumWidth(999)
                    cell_lay.addWidget(tag)

                cell_lay.addStretch()
                self._grid.addWidget(cell, row, col)


# ── CalendarWidget (top-level, owns the view switcher) ───────────────────────

class CalendarWidget(QWidget):
    def __init__(self, store: Store, parent=None):
        super().__init__(parent)
        self._store    = store
        self._ref_date = date.today()
        self._view     = "week"   # "week" | "day" | "month"
        self._build()
        self.refresh()

    # ── build ────────────────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        # ── toolbar ──
        bar = QHBoxLayout()

        _sm_style = ("QPushButton { padding: 4px 8px; }"
                     f"QPushButton[flat=true] {{ padding: 4px 8px; "
                     f"color: {PALETTE['accent']}; background: transparent; "
                     f"border: 1px solid {PALETTE['accent']}; border-radius: 5px; }}"
                     f"QPushButton[flat=true]:hover {{ background: {PALETTE['accent_light']}; }}")

        # view switcher buttons – order: 日 / 周 / 月
        self._view_btns: dict[str, QPushButton] = {}
        for label, key in [("日", "day"), ("周", "week"), ("月", "month")]:
            btn = QPushButton(label)
            btn.setProperty("flat", True)
            btn.setStyleSheet(_sm_style)
            btn.clicked.connect(lambda _, k=key: self._switch_view(k))
            bar.addWidget(btn)
            self._view_btns[key] = btn

        self._prev_btn = QPushButton("←")
        self._prev_btn.setProperty("flat", True)
        self._prev_btn.setStyleSheet(_sm_style)
        self._prev_btn.clicked.connect(self._go_prev)

        self._next_btn = QPushButton("→")
        self._next_btn.setProperty("flat", True)
        self._next_btn.setStyleSheet(_sm_style)
        self._next_btn.clicked.connect(self._go_next)

        self._period_lbl = QLabel()
        self._period_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        today_btn = QPushButton("今天")
        today_btn.setStyleSheet("QPushButton { padding: 4px 8px; }")
        today_btn.clicked.connect(self._go_today)

        bar.addWidget(self._prev_btn)
        bar.addWidget(self._period_lbl, 1)
        bar.addWidget(self._next_btn)
        bar.addWidget(today_btn)
        root.addLayout(bar)

        # ── stacked content ──
        self._stack = QStackedWidget()
        root.addWidget(self._stack, 1)

        # week view
        self._week_widget = QWidget()
        ww_lay = QVBoxLayout(self._week_widget)
        ww_lay.setContentsMargins(0, 0, 0, 0)
        ww_lay.setSpacing(0)

        self._week_hdr = QHBoxLayout()
        self._week_hdr.setSpacing(0)
        self._week_hdr.addSpacing(TIME_W)
        self._day_labels: list[QLabel] = []
        for _ in range(7):
            lbl = QLabel()
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setFixedWidth(DAY_W)
            lbl.setFixedHeight(34)
            self._day_labels.append(lbl)
            self._week_hdr.addWidget(lbl)
        ww_lay.addLayout(self._week_hdr)

        self._week_scroll = QScrollArea()
        self._week_scroll.setWidgetResizable(False)
        self._week_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._week_grid: TimeGrid | None = None
        ww_lay.addWidget(self._week_scroll, 1)
        self._stack.addWidget(self._week_widget)

        # day view
        self._day_widget = QWidget()
        dw_lay = QVBoxLayout(self._day_widget)
        dw_lay.setContentsMargins(0, 0, 0, 0)
        dw_lay.setSpacing(0)
        self._day_hdr_lbl = QLabel()
        self._day_hdr_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._day_hdr_lbl.setFixedHeight(34)
        self._day_hdr_lbl.setStyleSheet("font-weight:bold;font-size:14px;")
        dw_lay.addWidget(self._day_hdr_lbl)
        self._day_scroll = QScrollArea()
        self._day_scroll.setWidgetResizable(False)
        self._day_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._day_grid: TimeGrid | None = None
        dw_lay.addWidget(self._day_scroll, 1)
        self._stack.addWidget(self._day_widget)

        # month view
        self._month_view = MonthView(self._store)
        self._stack.addWidget(self._month_view)

    # ── navigation ───────────────────────────────────────────────────

    def _switch_view(self, key: str):
        self._view = key
        self.refresh()

    def _go_prev(self):
        if self._view == "week":
            self._ref_date -= timedelta(weeks=1)
        elif self._view == "day":
            self._ref_date -= timedelta(days=1)
        else:
            d = self._ref_date.replace(day=1) - timedelta(days=1)
            self._ref_date = d.replace(day=1)
        self.refresh()

    def _go_next(self):
        if self._view == "week":
            self._ref_date += timedelta(weeks=1)
        elif self._view == "day":
            self._ref_date += timedelta(days=1)
        else:
            d = self._ref_date.replace(day=28) + timedelta(days=4)
            self._ref_date = d.replace(day=1)
        self.refresh()

    def _go_today(self):
        self._ref_date = date.today()
        self.refresh()

    # ── refresh ──────────────────────────────────────────────────────

    def refresh(self):
        if self._view == "week":
            self._refresh_week()
            self._stack.setCurrentWidget(self._week_widget)
        elif self._view == "day":
            self._refresh_day()
            self._stack.setCurrentWidget(self._day_widget)
        else:
            self._month_view._ref_date = self._ref_date
            self._month_view.refresh()
            self._period_lbl.setText(self._ref_date.strftime("%Y年%m月"))
            self._stack.setCurrentWidget(self._month_view)

    def _cal_settings(self):
        s = self._store.settings
        return (
            getattr(s, "cal_hour_h",  HOUR_H),
            getattr(s, "cal_start_h", START_H),
            getattr(s, "cal_end_h",   END_H),
            getattr(s, "cal_day_w",   DAY_W),
        )

    def _make_grid(self, dates: list[date], day_w: int) -> TimeGrid:
        hour_h, start_h, end_h, _ = self._cal_settings()
        g = TimeGrid(dates, self._store, day_w,
                     hour_h=hour_h, start_h=start_h, end_h=end_h)
        g.block_clicked.connect(self._on_block_clicked)
        g.block_moved.connect(self._on_block_moved)
        g.block_resized.connect(self._on_block_resized)
        g.empty_clicked.connect(self._on_empty_clicked)
        g.memo_dropped.connect(self._on_memo_dropped)
        return g

    def _refresh_week(self):
        dates     = _week_dates(self._ref_date)
        date_strs = [d.isoformat() for d in dates]
        today     = date.today()

        self._period_lbl.setText(
            f"{dates[0].strftime('%Y/%m/%d')} – {dates[-1].strftime('%m/%d')}"
        )
        for i, (d, lbl) in enumerate(zip(dates, self._day_labels)):
            lbl.setText(f"{WEEK_HEADERS[i]}\n{d.month}/{d.day}")
            lbl.setStyleSheet(
                f"background:{PALETTE['accent']};color:white;"
                "border-radius:4px;font-weight:bold;"
                if d == today else ""
            )

        hour_h, start_h, end_h, day_w = self._cal_settings()
        for lbl in self._day_labels:
            lbl.setFixedWidth(day_w)
        blocks = self._store.blocks_for_week(date_strs)
        items  = [BlockItem(b, date_strs.index(b.date), day_w,
                            hour_h=hour_h, start_h=start_h)
                  for b in blocks]

        # replace grid widget
        _saved_scroll = self._week_scroll.verticalScrollBar().value()
        if self._week_grid:
            self._week_grid.deleteLater()
        self._week_grid = self._make_grid(dates, day_w)
        self._week_grid.set_items(items)
        self._week_scroll.setWidget(self._week_grid)
        default_scroll = max(0, (8 - start_h)) * hour_h
        self._week_scroll.verticalScrollBar().setValue(
            _saved_scroll if _saved_scroll > 0 else default_scroll
        )
        self._dates     = dates
        self._date_strs = date_strs

    def _refresh_day(self):
        d         = self._ref_date
        date_str  = d.isoformat()
        today     = date.today()
        day_w     = max(200, self.width() - TIME_W - 20)

        self._period_lbl.setText(d.strftime("%Y年%m月%d日"))
        self._day_hdr_lbl.setText(
            d.strftime("%Y年%m月%d日 ") + WEEK_HEADERS[d.weekday()]
        )
        if d == today:
            self._day_hdr_lbl.setStyleSheet(
                f"font-weight:bold;font-size:14px;"
                f"color:{PALETTE['accent']};"
            )
        else:
            self._day_hdr_lbl.setStyleSheet(
                "font-weight:bold;font-size:14px;"
            )

        hour_h, start_h, end_h, _ = self._cal_settings()
        blocks = [b for b in self._store.time_blocks if b.date == date_str]
        items  = [BlockItem(b, 0, day_w, hour_h=hour_h, start_h=start_h)
                  for b in blocks]

        _saved_scroll = self._day_scroll.verticalScrollBar().value()
        if self._day_grid:
            self._day_grid.deleteLater()
        self._day_grid = self._make_grid([d], day_w)
        self._day_grid.set_items(items)
        self._day_scroll.setWidget(self._day_grid)
        default_scroll = max(0, (8 - start_h)) * hour_h
        self._day_scroll.verticalScrollBar().setValue(
            _saved_scroll if _saved_scroll > 0 else default_scroll
        )
        self._dates     = [d]
        self._date_strs = [date_str]

    # ── interaction handlers ─────────────────────────────────────────

    def _on_block_clicked(self, item: BlockItem):
        # Use singleShot to defer the dialog so we exit mouseReleaseEvent first,
        # preventing the TimeGrid from being deleted while still on the call stack.
        QTimer.singleShot(0, lambda: self._open_block_dialog(item))

    def _open_block_dialog(self, item: BlockItem):
        dlg = BlockEditDialog(item.block, self._store.memo_tasks, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            if dlg.is_deleted():
                self._store.delete_block(item.block.id)
            else:
                dlg.apply_to(item.block)
                self._store.update_block(item.block)
            self.refresh()

    def _on_block_moved(self, block_id: str, new_date: str, new_hm: str):
        block = next((b for b in self._store.time_blocks if b.id == block_id), None)
        if not block:
            return
        dur = _duration_min(block.start_time, block.end_time)
        block.date       = new_date
        block.start_time = new_hm
        block.end_time   = _add_min(new_hm, dur)
        self._store.update_block(block)
        QTimer.singleShot(0, self.refresh)

    def _on_block_resized(self, block_id: str, new_end: str):
        block = next((b for b in self._store.time_blocks if b.id == block_id), None)
        if not block:
            return
        block.end_time = new_end
        self._store.update_block(block)
        QTimer.singleShot(0, self.refresh)

    def _on_empty_clicked(self, date_str: str, hm_str: str):
        QTimer.singleShot(0, lambda: self._open_new_block_dialog(date_str, hm_str))

    def _open_new_block_dialog(self, date_str: str, hm_str: str):
        dlg = NewBlockDialog(date_str, hm_str, self._store.memo_tasks, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._store.add_block(dlg.build_block())
            self.refresh()

    def _on_memo_dropped(self, task_id: str, date_str: str, hm_str: str):
        task = next((t for t in self._store.memo_tasks if t.id == task_id), None)
        if not task:
            return
        block = TimeBlock(
            title=task.title, date=date_str,
            start_time=hm_str, end_time=_add_min(hm_str, 60),
            memo_task_id=task.id, is_planned=True,
        )
        self._store.add_block(block)
        self.refresh()

    def add_block_from_session(self, block: TimeBlock):
        """Called by pomodoro controller after a session completes."""
        self._store.add_block(block)
        self.refresh()
