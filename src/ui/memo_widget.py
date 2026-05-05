"""
Four-quadrant memo widget.
Supports: add task, drag between quadrants, drag OUT to calendar,
mark done, delete.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QFrame, QScrollArea, QPushButton,
    QLineEdit, QDialog, QDialogButtonBox, QTextEdit,
    QSizePolicy, QApplication, QMenu, QSpinBox,
    QComboBox, QDateEdit, QTimeEdit, QFormLayout,
)
from PyQt6.QtCore import Qt, pyqtSignal, QMimeData, QPoint, QDate, QTime, QTimer
from PyQt6.QtGui import QDrag, QPixmap, QPainter, QColor, QFont, QAction, QFontMetrics
from datetime import datetime as _dt


class ElidedLabel(QLabel):
    """QLabel that elides text with '…' when width is too small."""
    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._full_text = text
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )

    def set_full_text(self, text: str):
        self._full_text = text
        self._elide()

    def minimumSizeHint(self):
        # Return zero minimum width so layout is free to shrink us
        hint = super().minimumSizeHint()
        hint.setWidth(0)
        return hint

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._elide()

    def _elide(self):
        fm = QFontMetrics(self.font())
        elided = fm.elidedText(
            self._full_text, Qt.TextElideMode.ElideRight, max(self.width(), 0)
        )
        super().setText(elided)
        self.setToolTip(self._full_text if elided != self._full_text else "")


def _lighten_hex(hex_color: str, factor: float = 0.45) -> str:
    """Return a lighter version of hex_color by blending toward white."""
    c = QColor(hex_color)
    r = int(c.red()   + (255 - c.red())   * factor)
    g = int(c.green() + (255 - c.green()) * factor)
    b = int(c.blue()  + (255 - c.blue())  * factor)
    return QColor(r, g, b).name()

from src.core.models import MemoTask, QUADRANTS
from src.core.store import Store
from src.ui.theme import PALETTE

QUADRANT_COLORS = {
    1: (PALETTE["q1"],        PALETTE["q1_header"],  "重要且紧急"),
    2: (PALETTE["q2"],        PALETTE["q2_header"],  "重要不紧急"),
    3: (PALETTE["q3"],        PALETTE["q3_header"],  "紧急不重要"),
    4: (PALETTE["q4"],        PALETTE["q4_header"],  "不重要不紧急"),
}

MIME_TYPE = "application/x-memotask-id"


class TaskCard(QFrame):
    """Draggable card for a single MemoTask."""

    delete_requested    = pyqtSignal(str)
    toggle_done         = pyqtSignal(str)
    edit_requested      = pyqtSignal(str)   # task_id → open edit dialog
    schedule_requested  = pyqtSignal(str)   # task_id → open recurring dialog

    def __init__(self, task: MemoTask, parent=None):
        super().__init__(parent)
        self.task = task
        self._drag_start: QPoint | None = None
        self._build()

    def _build(self):
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(f"""
            QFrame {{
                background: white;
                border: 1px solid {PALETTE['border']};
                border-radius: 6px;
                padding: 2px;
            }}
        """)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(2)

        # parse creation time once
        _date_short = ""
        _date_full  = ""
        if self.task.created_at:
            try:
                _dt_obj    = _dt.fromisoformat(self.task.created_at)
                _date_short = f"{_dt_obj.month}.{_dt_obj.day}"
                _date_full  = _dt_obj.strftime("%Y年%m月%d日 %H:%M 创建")
            except Exception:
                pass

        # title row: [title elided] [date] [✓] [✕]
        row = QHBoxLayout()
        row.setSpacing(4)

        self._lbl = ElidedLabel(self.task.title)
        font = self._lbl.font()
        if self.task.done:
            font.setStrikeOut(True)
            self._lbl.setStyleSheet(f"color:{PALETTE['text_sub']};")
        self._lbl.setFont(font)
        row.addWidget(self._lbl, 1)

        if _date_short:
            date_lbl = QLabel(_date_short)
            date_lbl.setStyleSheet(
                f"color:{PALETTE['text_sub']};font-size:10px;"
            )
            date_lbl.setToolTip(_date_full)
            date_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
            row.addWidget(date_lbl)

        done_btn = QPushButton("✓")
        done_btn.setFixedSize(24, 24)
        done_btn.setToolTip("标记完成")
        if self.task.done:
            done_btn.setStyleSheet(
                "background:#66BB6A; color:white; border-radius:12px; border:none;"
                "font-size:13px; font-weight:bold;"
            )
        else:
            done_btn.setStyleSheet(
                f"background:{PALETTE['surface2']}; color:{PALETTE['text_sub']};"
                "border-radius:12px; border:1px solid #bbb; font-size:13px;"
            )
        done_btn.clicked.connect(lambda: self.toggle_done.emit(self.task.id))
        row.addWidget(done_btn)

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(24, 24)
        del_btn.setToolTip("删除")
        del_btn.setStyleSheet(
            f"background:{PALETTE['surface2']}; color:#E53935;"
            "border-radius:12px; border:1px solid #bbb; font-size:11px; font-weight:bold;"
        )
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self.task.id))
        row.addWidget(del_btn)

        lay.addLayout(row)

        # note row — elided, single line
        if self.task.note:
            note_lbl = ElidedLabel(self.task.note)
            note_lbl.setStyleSheet(f"color:{PALETTE['text_sub']};font-size:11px;")
            lay.addWidget(note_lbl)

    # --- Drag support ---

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._drag_start = ev.pos()
        super().mousePressEvent(ev)

    def mouseDoubleClickEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.edit_requested.emit(self.task.id)
        super().mouseDoubleClickEvent(ev)

    def mouseMoveEvent(self, ev):
        if (self._drag_start and
                (ev.pos() - self._drag_start).manhattanLength() > 8):
            self._start_drag()
        super().mouseMoveEvent(ev)

    def _start_drag(self):
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(MIME_TYPE, self.task.id.encode())
        drag.setMimeData(mime)

        pix = QPixmap(self.size())
        pix.fill(QColor(0, 0, 0, 0))
        painter = QPainter(pix)
        self.render(painter)
        painter.end()
        drag.setPixmap(pix)
        drag.setHotSpot(self._drag_start)
        drag.exec(Qt.DropAction.MoveAction)
        self._drag_start = None

    def contextMenuEvent(self, ev):
        menu = QMenu(self)
        sched_label = "修改定时任务" if self.task.schedule else "创建定时任务"
        act_sched = QAction(sched_label, self)
        act_sched.triggered.connect(lambda: self.schedule_requested.emit(self.task.id))
        menu.addAction(act_sched)
        if self.task.schedule:
            act_del_sched = QAction("取消定时任务", self)
            act_del_sched.triggered.connect(lambda: self.schedule_requested.emit("__clear__:" + self.task.id))
            menu.addAction(act_del_sched)
        menu.exec(ev.globalPos())


class QuadrantPanel(QFrame):
    """Single quadrant cell with a drop zone."""

    task_dropped    = pyqtSignal(str, int)   # task_id, new_quadrant
    delete_requested_ext = pyqtSignal(str)   # task_id → let MemoWidget handle undo

    def __init__(self, quadrant: int, parent=None):
        super().__init__(parent)
        self.quadrant = quadrant
        bg, header, label = QUADRANT_COLORS[quadrant]
        self._bg    = bg
        self._label = label
        self.setAcceptDrops(True)
        self.setStyleSheet(f"background:{bg}; border-radius:8px;")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # header — click to add task
        self._hdr = QLabel(f"  {label}  ＋")
        self._hdr.setFixedHeight(28)
        self._hdr.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hdr.setStyleSheet(
            f"background:{header}; border-radius:8px 8px 0 0;"
            "font-weight:bold; font-size:12px;"
        )
        self._hdr.mousePressEvent = lambda _: self._on_add()
        root.addWidget(self._hdr)

        # scrollable card list
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(f"background:{bg};")

        self._container = QWidget()
        self._container.setStyleSheet(f"background:{bg};")
        self._card_layout = QVBoxLayout(self._container)
        self._card_layout.setContentsMargins(6, 6, 6, 6)
        self._card_layout.setSpacing(4)
        self._card_layout.addStretch(1)

        self._scroll.setWidget(self._container)
        root.addWidget(self._scroll, 1)

        # add button
        add_btn = QPushButton("+ 添加任务")
        add_btn.setStyleSheet(
            f"background:transparent; color:{PALETTE['text_sub']};"
            "border:none; font-size:12px; text-align:left; padding:4px 8px;"
        )
        add_btn.clicked.connect(self._on_add)
        root.addWidget(add_btn)

        self._store: Store | None = None

    def set_store(self, store: Store):
        self._store = store

    def apply_color(self, header_color: str):
        bg = _lighten_hex(header_color, 0.55)
        self._hdr.setStyleSheet(
            f"background:{header_color}; border-radius:8px 8px 0 0;"
            "font-weight:bold; font-size:12px;"
        )
        self.setStyleSheet(f"background:{bg}; border-radius:8px;")
        self._scroll.setStyleSheet(f"background:{bg};")
        self._container.setStyleSheet(f"background:{bg};")

    def add_card(self, task: MemoTask, prepend: bool = False):
        card = TaskCard(task)
        card.delete_requested.connect(self._on_delete)
        card.toggle_done.connect(self._on_toggle_done)
        card.edit_requested.connect(self._on_edit)
        card.schedule_requested.connect(self._on_schedule)
        if prepend:
            self._card_layout.insertWidget(0, card)
        else:
            # insert before the trailing stretch
            self._card_layout.insertWidget(self._card_layout.count() - 1, card)

    def clear_cards(self):
        while self._card_layout.count() > 1:
            item = self._card_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _on_add(self):
        dlg = AddTaskDialog(self.quadrant, self)
        if dlg.exec() == QDialog.DialogCode.Accepted and self._store:
            task = MemoTask(
                title=dlg.title(),
                note=dlg.note(),
                quadrant=self.quadrant,
            )
            self._store.add_memo(task)
            self._refresh()

    def _on_edit(self, task_id: str):
        if not self._store:
            return
        task = next((t for t in self._store.memo_tasks if t.id == task_id), None)
        if not task:
            return
        dlg = AddTaskDialog(self.quadrant, self,
                            prefill_title=task.title, prefill_note=task.note)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_title = dlg.title()
            if new_title:
                task.title = new_title
                task.note  = dlg.note()
                self._store.update_memo(task)
                self._refresh()

    def _on_delete(self, task_id: str):
        # Remove from UI immediately; MemoWidget handles store + undo
        for i in range(self._card_layout.count()):
            w = self._card_layout.itemAt(i).widget()
            if isinstance(w, TaskCard) and w.task.id == task_id:
                self._card_layout.takeAt(i)
                w.deleteLater()
                break
        self.delete_requested_ext.emit(task_id)

    def _on_toggle_done(self, task_id: str):
        if not self._store:
            return
        for t in self._store.memo_tasks:
            if t.id == task_id:
                t.done = not t.done
                self._store.update_memo(t)
                break
        self._refresh()

    def _on_schedule(self, payload: str):
        if not self._store:
            return
        # "__clear__:task_id" = remove schedule
        if payload.startswith("__clear__:"):
            task_id = payload[len("__clear__:"):]
            for t in self._store.memo_tasks:
                if t.id == task_id:
                    t.schedule = ""
                    self._store.update_memo(t)
                    break
            self._refresh()
            return
        task_id = payload
        task = next((t for t in self._store.memo_tasks if t.id == task_id), None)
        if not task:
            return
        dlg = RecurringTaskDialog(task.title, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            task.schedule = dlg.schedule_str()
            self._store.update_memo(task)
            self._refresh()

    def _refresh(self):
        if not self._store:
            return
        self.clear_cards()
        tasks = [t for t in self._store.memo_tasks
                 if t.quadrant == self.quadrant and not t.deleted]
        # sort by created_at descending (newest first within each group)
        tasks.sort(key=lambda t: t.created_at or "", reverse=True)
        for t in tasks:
            if not t.done:
                self.add_card(t)
        for t in tasks:
            if t.done:
                self.add_card(t)

    # --- Drop ---

    def dragEnterEvent(self, ev):
        if ev.mimeData().hasFormat(MIME_TYPE):
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        task_id = ev.mimeData().data(MIME_TYPE).data().decode()
        self.task_dropped.emit(task_id, self.quadrant)
        ev.acceptProposedAction()


class RecurringTaskDialog(QDialog):
    """Configure a recurring schedule for a MemoTask."""

    _FREQ_LABELS = [
        ("每天",   "daily"),
        ("每周一", "weekly-0"),
        ("每周二", "weekly-1"),
        ("每周三", "weekly-2"),
        ("每周四", "weekly-3"),
        ("每周五", "weekly-4"),
        ("每周六", "weekly-5"),
        ("每周日", "weekly-6"),
        ("每月固定日", "monthly"),
    ]

    def __init__(self, task_title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"创建定时任务 — {task_title}")
        self.setMinimumWidth(360)
        lay = QFormLayout(self)

        self._freq_combo = QComboBox()
        for label, _ in self._FREQ_LABELS:
            self._freq_combo.addItem(label)
        lay.addRow("重复频率", self._freq_combo)

        self._month_day_spin = QSpinBox()
        self._month_day_spin.setRange(1, 31)
        self._month_day_spin.setValue(1)
        self._month_day_spin.setSuffix(" 号")
        self._month_day_spin.setVisible(False)
        lay.addRow("每月日期", self._month_day_spin)
        self._freq_combo.currentIndexChanged.connect(self._on_freq_changed)

        self._time_edit = QTimeEdit(QTime(9, 0))
        self._time_edit.setDisplayFormat("HH:mm")
        lay.addRow("开始时间", self._time_edit)

        self._dur_spin = QSpinBox()
        self._dur_spin.setRange(5, 480)
        self._dur_spin.setValue(60)
        self._dur_spin.setSuffix(" 分钟")
        lay.addRow("持续时长", self._dur_spin)

        self._end_date = QDateEdit(QDate.currentDate().addMonths(3))
        self._end_date.setCalendarPopup(True)
        self._end_date.setDisplayFormat("yyyy-MM-dd")
        lay.addRow("结束日期（含）", self._end_date)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.setStyleSheet(
            "QPushButton { background:#EFEFEF; color:#1A1A1A; border:1px solid #bbb;"
            "border-radius:5px; padding:5px 18px; }"
            "QPushButton:hover { background:#E0E0E0; }"
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addRow(btns)

    def _on_freq_changed(self, idx: int):
        self._month_day_spin.setVisible(
            self._FREQ_LABELS[idx][1] == "monthly"
        )

    def schedule_str(self) -> str:
        idx = self._freq_combo.currentIndex()
        freq_key = self._FREQ_LABELS[idx][1]
        if freq_key == "monthly":
            freq_key = f"monthly-{self._month_day_spin.value()}"
        time_str = self._time_edit.time().toString("HH:mm")
        dur = self._dur_spin.value()
        end = self._end_date.date().toString("yyyy-MM-dd")
        return f"{freq_key}|{time_str}|{dur}|{end}"


class AddTaskDialog(QDialog):
    def __init__(self, quadrant: int, parent=None,
                 prefill_title: str = "", prefill_note: str = ""):
        super().__init__(parent)
        is_edit = bool(prefill_title)
        self.setWindowTitle(
            f"{'编辑' if is_edit else '添加'}任务 – {QUADRANT_COLORS[quadrant][2]}"
        )
        self.setMinimumWidth(320)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("任务名称"))
        self._title = QLineEdit(prefill_title)
        lay.addWidget(self._title)
        lay.addWidget(QLabel("备注（可选）"))
        self._note = QTextEdit()
        self._note.setFixedHeight(72)
        self._note.setPlainText(prefill_note)
        lay.addWidget(self._note)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.setStyleSheet(
            "QPushButton { background: #EFEFEF; color: #1A1A1A; border: 1px solid #bbb;"
            "border-radius: 5px; padding: 5px 18px; }"
            "QPushButton:hover { background: #E0E0E0; }"
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def title(self) -> str:
        return self._title.text().strip()

    def note(self) -> str:
        return self._note.toPlainText().strip()


class MemoWidget(QWidget):
    """
    Full four-quadrant memo panel.
    Emits task_to_calendar(task_id) when a card is dragged onto the calendar
    (the calendar widget listens for the same MIME_TYPE).
    """

    _UNDO_SECONDS = 5   # seconds before deletion is committed to disk

    def __init__(self, store: Store, parent=None):
        super().__init__(parent)
        self._store = store
        self._panels: dict[int, QuadrantPanel] = {}
        self._build()
        self._load()

    def _build(self):
        grid = QGridLayout(self)
        grid.setSpacing(8)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        for q in range(1, 5):
            panel = QuadrantPanel(q)
            panel.set_store(self._store)
            panel.task_dropped.connect(self._on_task_dropped)
            panel.delete_requested_ext.connect(self._on_delete)
            row, col = divmod(q - 1, 2)
            grid.addWidget(panel, row, col)
            self._panels[q] = panel
        self._apply_colors()

    def _on_delete(self, task_id: str):
        self._store.delete_memo(task_id)

    def _load(self):
        for q, panel in self._panels.items():
            panel.clear_cards()
            tasks = [t for t in self._store.memo_tasks
                     if t.quadrant == q and not t.deleted]
            tasks.sort(key=lambda t: t.created_at or "", reverse=True)
            for t in tasks:
                if not t.done:
                    panel.add_card(t)
            for t in tasks:
                if t.done:
                    panel.add_card(t)

    def _on_task_dropped(self, task_id: str, new_quadrant: int):
        for t in self._store.memo_tasks:
            if t.id == task_id:
                if t.quadrant == new_quadrant:
                    return
                old_q = t.quadrant
                t.quadrant = new_quadrant
                self._store.update_memo(t)
                # remove from old panel, add to new
                self._panels[old_q]._refresh()
                self._panels[new_quadrant].add_card(t)
                return

    def refresh(self):
        self._load()
        self._apply_colors()

    def _apply_colors(self):
        colors = getattr(self._store.settings, "quadrant_colors", None)
        if not colors or len(colors) < 4:
            return
        for q, panel in self._panels.items():
            panel.apply_color(colors[q - 1])
