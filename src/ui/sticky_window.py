"""
Sticky notes window — independent notepad, does not affect main app.
"""

from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
    QPushButton, QLabel, QLineEdit, QPlainTextEdit,
    QFrame, QMessageBox, QSizePolicy,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QCursor

from src.core.models import StickyNote
from src.core.store import Store


_PIN_ON     = "📌 已置顶"
_PIN_OFF    = "📌 置顶"
_COLLAPSE   = "▲ 收起"
_EXPAND     = "▼ 展开"
_PINNED_BG  = "#FFFDE7"
_NORMAL_BG  = "#FAFAFA"
_BORDER     = "#E0E0E0"
_MIN_HEIGHT = 100       # minimum card height when expanded (px)
_HANDLE_H   = 8         # resize-handle strip height (px)


class _ResizeHandle(QWidget):
    """Draggable strip at the bottom of a StickyCard for height resizing."""

    def __init__(self, card: "StickyCard"):
        super().__init__(card)
        self._card = card
        self._drag_start_y: int | None = None
        self._drag_start_h: int | None = None
        self.setFixedHeight(_HANDLE_H)
        self.setCursor(QCursor(Qt.CursorShape.SizeVerCursor))
        self.setStyleSheet("background:#ddd; border-radius:3px;")

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._drag_start_y = ev.globalPosition().toPoint().y()
            self._drag_start_h = self._card.height()

    def mouseMoveEvent(self, ev):
        if self._drag_start_y is None:
            return
        delta = ev.globalPosition().toPoint().y() - self._drag_start_y
        new_h = max(_MIN_HEIGHT, self._drag_start_h + delta)
        self._card.setFixedHeight(new_h)

    def mouseReleaseEvent(self, ev):
        if self._drag_start_y is not None:
            self._card._note.card_height = self._card.height()
            self._card._store.update_sticky(self._card._note)
            self._drag_start_y = None
            self._drag_start_h = None


class StickyCard(QFrame):
    """One sticky-note card, inline editable."""

    def __init__(self, note: StickyNote, store: Store, window: "StickyWindow"):
        super().__init__()
        self._note        = note
        self._store       = store
        self._window      = window
        self._save_timer  = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(300)
        self._save_timer.timeout.connect(self._flush_save)
        self._build()
        self._apply_pin_style()
        self._apply_collapse()
        # restore saved height (must happen after collapse applied)
        if note.card_height >= _MIN_HEIGHT and not note.collapsed:
            self.setFixedHeight(note.card_height)

    # ── build ─────────────────────────────────────────────────────────

    def _build(self):
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setLineWidth(1)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 4)
        root.setSpacing(6)

        # ── top bar: pin | collapse | created_at | delete ──────────────
        top = QHBoxLayout()
        top.setSpacing(6)

        self._pin_btn = QPushButton(_PIN_ON if self._note.pinned else _PIN_OFF)
        self._pin_btn.setFixedHeight(24)
        self._pin_btn.setStyleSheet(
            "font-size:11px; padding:0 6px; border:1px solid #ccc; border-radius:4px;"
        )
        self._pin_btn.clicked.connect(self._toggle_pin)
        top.addWidget(self._pin_btn)

        self._collapse_btn = QPushButton(
            _COLLAPSE if not self._note.collapsed else _EXPAND
        )
        self._collapse_btn.setFixedHeight(24)
        self._collapse_btn.setStyleSheet(
            "font-size:11px; padding:0 6px; border:1px solid #ccc; border-radius:4px;"
        )
        self._collapse_btn.clicked.connect(self._toggle_collapse)
        top.addWidget(self._collapse_btn)

        try:
            dt = datetime.fromisoformat(self._note.created_at)
            date_str = f"{dt.month}.{dt.day}  {dt.hour:02d}:{dt.minute:02d}"
        except Exception:
            date_str = ""
        date_lbl = QLabel(date_str)
        date_lbl.setStyleSheet("color:#aaa; font-size:11px;")
        top.addWidget(date_lbl, 1)

        del_btn = QPushButton("🗑 删除")
        del_btn.setFixedHeight(24)
        del_btn.setStyleSheet(
            "font-size:11px; padding:0 6px; border:1px solid #f99; "
            "border-radius:4px; color:#c00;"
        )
        del_btn.clicked.connect(self._delete)
        top.addWidget(del_btn)

        root.addLayout(top)

        # ── title ──────────────────────────────────────────────────────
        self._title_edit = QLineEdit(self._note.title)
        self._title_edit.setPlaceholderText("标题…")
        f = QFont()
        f.setPointSize(12)
        f.setBold(True)
        self._title_edit.setFont(f)
        self._title_edit.setStyleSheet(
            "border:none; border-bottom:1px solid #ddd; "
            "background:transparent; padding:2px 0;"
        )
        self._title_edit.editingFinished.connect(self._schedule_save)
        root.addWidget(self._title_edit)

        # ── body (hidden when collapsed) ───────────────────────────────
        self._body_edit = QPlainTextEdit(self._note.body)
        self._body_edit.setPlaceholderText("在此输入内容…")
        self._body_edit.setMinimumHeight(50)
        self._body_edit.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._body_edit.setStyleSheet(
            "border:none; background:transparent; padding:0;"
        )
        self._body_edit.textChanged.connect(self._schedule_save)
        root.addWidget(self._body_edit, 1)

        # ── resize handle (hidden when collapsed) ─────────────────────
        self._handle = _ResizeHandle(self)
        root.addWidget(self._handle)

    # ── styling ───────────────────────────────────────────────────────

    def _apply_pin_style(self):
        bg = _PINNED_BG if self._note.pinned else _NORMAL_BG
        self.setStyleSheet(
            f"StickyCard {{ background:{bg}; border:1px solid {_BORDER}; "
            "border-radius:8px; }}"
        )
        self._pin_btn.setText(_PIN_ON if self._note.pinned else _PIN_OFF)

    def _apply_collapse(self):
        collapsed = self._note.collapsed
        self._body_edit.setVisible(not collapsed)
        self._handle.setVisible(not collapsed)
        self._collapse_btn.setText(_EXPAND if collapsed else _COLLAPSE)
        if collapsed:
            # let Qt pick the natural compact height
            self.setMaximumHeight(16_777_215)
            self.setFixedHeight(self.sizeHint().height())
        else:
            # restore to either saved height or auto
            self.setMaximumHeight(16_777_215)
            h = self._note.card_height
            if h >= _MIN_HEIGHT:
                self.setFixedHeight(h)
            else:
                self.setMinimumHeight(_MIN_HEIGHT)

    # ── actions ───────────────────────────────────────────────────────

    def _schedule_save(self):
        self._save_timer.start()

    def _flush_save(self):
        self._note.title = self._title_edit.text().strip()
        self._note.body  = self._body_edit.toPlainText()
        self._store.update_sticky(self._note)

    def _toggle_pin(self):
        self._flush_save()
        self._note.pinned = not self._note.pinned
        self._store.update_sticky(self._note)
        self._apply_pin_style()
        self._window.reorder_cards()

    def _toggle_collapse(self):
        self._flush_save()
        self._note.collapsed = not self._note.collapsed
        self._store.update_sticky(self._note)
        self._apply_collapse()

    def _delete(self):
        title = self._note.title or "（无标题）"
        ret = QMessageBox.question(
            self, "确认删除",
            f"确定要删除便利贴「{title}」吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        self._save_timer.stop()
        self._store.delete_sticky(self._note.id)
        self._window.remove_card(self)

    # ── public ────────────────────────────────────────────────────────

    @property
    def note(self) -> StickyNote:
        return self._note


class StickyWindow(QWidget):
    """Standalone sticky-notes window."""

    def __init__(self, store: Store, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self._store = store
        self._cards: list[StickyCard] = []
        self.setWindowTitle("便利贴")
        self.resize(440, 620)
        self._build()
        self._load()

    # ── build ─────────────────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        bar = QHBoxLayout()
        bar.addStretch(1)
        add_btn = QPushButton("＋  新建便利贴")
        add_btn.setFixedHeight(32)
        add_btn.setStyleSheet(
            "background:#4A90D9; color:white; font-size:13px; "
            "border:none; border-radius:6px; padding:0 16px;"
        )
        add_btn.clicked.connect(self._new_sticky)
        bar.addWidget(add_btn)
        root.addLayout(bar)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._container = QWidget()
        self._list_lay  = QVBoxLayout(self._container)
        self._list_lay.setContentsMargins(0, 0, 0, 0)
        self._list_lay.setSpacing(10)
        self._list_lay.addStretch()

        self._scroll.setWidget(self._container)
        root.addWidget(self._scroll, 1)

    # ── load ──────────────────────────────────────────────────────────

    def _load(self):
        pinned   = sorted([n for n in self._store.stickies if n.pinned],
                          key=lambda n: n.created_at, reverse=True)
        unpinned = sorted([n for n in self._store.stickies if not n.pinned],
                          key=lambda n: n.created_at, reverse=True)
        for note in pinned + unpinned:
            self._insert_card(StickyCard(note, self._store, self))

    # ── card management ───────────────────────────────────────────────

    def _insert_card(self, card: StickyCard):
        pos = self._list_lay.count() - 1
        self._list_lay.insertWidget(pos, card)
        self._cards.append(card)

    def _new_sticky(self):
        note = StickyNote()
        self._store.add_sticky(note)
        card = StickyCard(note, self._store, self)
        insert_pos = self._pinned_count()
        self._list_lay.insertWidget(insert_pos, card)
        self._cards.insert(insert_pos, card)
        self._scroll.verticalScrollBar().setValue(0)
        card._title_edit.setFocus()

    def _pinned_count(self) -> int:
        return sum(1 for c in self._cards if c.note.pinned)

    def remove_card(self, card: StickyCard):
        self._list_lay.removeWidget(card)
        card.deleteLater()
        if card in self._cards:
            self._cards.remove(card)

    def reorder_cards(self):
        for card in self._cards:
            self._list_lay.removeWidget(card)

        pinned   = sorted([c for c in self._cards if c.note.pinned],
                          key=lambda c: c.note.created_at, reverse=True)
        unpinned = sorted([c for c in self._cards if not c.note.pinned],
                          key=lambda c: c.note.created_at, reverse=True)
        self._cards = pinned + unpinned

        for i, card in enumerate(self._cards):
            self._list_lay.insertWidget(i, card)
