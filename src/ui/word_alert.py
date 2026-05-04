"""
Word review full-screen alert shown at the end of each pomodoro segment,
or launched standalone via the "开始背单词" button.

Layout:
  Left panel  – scrollable word list with seen_count badges; click to jump
  Right panel – three-page flow per word:
    Page 1 – word + phonetic + EN definition + ZH definition
    Page 2 – example sentences (EN + ZH)
    Page 3 – type the word to confirm

End button logic:
  - Disabled until the user completes at least one word (reaches Page 3 and
    clicks 完成 / 知道了).
  - Once enabled: single click closes; long-press (1.5 s) also closes
    (useful when the button becomes enabled mid-hold).

Order toggle (top-right):  随机 ⚄  ↔  顺序 ↕
"""

import json
import random
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QStackedWidget, QApplication,
    QListWidget, QListWidgetItem, QFrame, QSplitter,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QSize
from PyQt6.QtGui import QFont, QColor

from src.ui.theme import PALETTE

WORDS_FILE    = Path(__file__).parent.parent.parent / "data" / "words.json"
FORCE_HOLD_MS = 1500


def _load_words() -> list:
    try:
        data = json.loads(WORDS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) and data else []
    except Exception:
        return []


class WordAlert(QWidget):
    """
    Full-screen word-review window.
    Emits `closed` when the user finishes or force-quits.

    Parameters
    ----------
    store : Store | None
        If provided, seen/correct counts are persisted via
        ``store.record_word_seen(word, correct)``.
    standalone : bool
        True  → launched from "开始背单词" button; no external pause/resume
                 side-effects expected.
        False → launched after a pomodoro segment; caller connects `closed`
                 to resume the engine.
    """

    closed = pyqtSignal()

    def __init__(self, store=None, standalone: bool = False, parent=None):
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

        self._store     = store
        self._standalone = standalone
        self._words     = _load_words()
        self._sequential = False   # False = random, True = sequential
        self._word_index = 0       # used in sequential mode
        self._word_done  = False   # True after first word completed
        self._current_correct = False  # spelling result for current word

        self._force_timer = QTimer(self)
        self._force_timer.setSingleShot(True)
        self._force_timer.setInterval(FORCE_HOLD_MS)
        self._force_timer.timeout.connect(self._do_close)

        # pick first word
        self._word = self._pick_next_word(advance=False)

        self._build()

    # ── word picking ──────────────────────────────────────────────────

    def _seen_count(self, word_str: str) -> int:
        if self._store:
            return self._store.word_progress.get(word_str, {}).get("seen_count", 0)
        return 0

    def _pick_next_word(self, advance: bool = True) -> dict | None:
        if not self._words:
            return None
        if self._sequential:
            if advance:
                self._word_index = (self._word_index + 1) % len(self._words)
            return self._words[self._word_index]
        else:
            return random.choice(self._words)

    # ── build ─────────────────────────────────────────────────────────

    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- Left: word list ----
        left = QFrame()
        left.setFixedWidth(200)
        left.setStyleSheet(
            f"background:{PALETTE['surface2']}; border-right:1px solid {PALETTE['border']};"
        )
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(0)

        list_title = QLabel("  单词列表")
        list_title.setFixedHeight(36)
        list_title.setStyleSheet(
            f"background:{PALETTE['surface2']}; font-weight:bold; font-size:13px;"
            f"border-bottom:1px solid {PALETTE['border']};"
        )
        left_lay.addWidget(list_title)

        self._word_list = QListWidget()
        self._word_list.setStyleSheet(
            f"background:{PALETTE['surface2']}; border:none; font-size:12px;"
        )
        self._word_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left_lay.addWidget(self._word_list, 1)
        self._populate_word_list()
        self._word_list.itemClicked.connect(self._on_list_click)

        root.addWidget(left)

        # ---- Right: title bar + stack + nav ----
        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(80, 60, 80, 60)
        right_lay.setSpacing(0)

        # title bar row
        title_row = QHBoxLayout()
        title_lbl = QLabel("休息时间 · 学一个单词")
        title_lbl.setStyleSheet(
            f"font-size:18px; font-weight:bold; color:{PALETTE['text_sub']};"
        )
        title_row.addWidget(title_lbl, 1)

        # order toggle button
        self._order_btn = QPushButton("随机 ⚄")
        self._order_btn.setStyleSheet(
            f"background:{PALETTE['surface2']}; color:{PALETTE['text_sub']};"
            "border:1px solid #ccc; border-radius:6px; padding:4px 12px; font-size:13px;"
        )
        self._order_btn.clicked.connect(self._toggle_order)
        title_row.addWidget(self._order_btn)

        # end button — always enabled for long-press; normal click only works
        # after first word is completed (_word_done=True)
        self._end_btn = QPushButton("结束（长按）")
        self._end_btn.setStyleSheet(self._end_btn_style_inactive())
        self._end_btn.pressed.connect(self._end_press)
        self._end_btn.released.connect(self._end_release)
        title_row.addWidget(self._end_btn)
        right_lay.addLayout(title_row)
        right_lay.addSpacing(30)

        # stacked pages
        self._stack = QStackedWidget()
        right_lay.addWidget(self._stack, 1)
        self._rebuild_pages()

        # bottom nav row
        right_lay.addSpacing(30)
        nav = QHBoxLayout()
        _nav_btn_style = (
            f"background:{PALETTE['surface2']}; color:{PALETTE['text']};"
            "border:1px solid #bbb; border-radius:8px; padding:8px 20px; font-size:14px;"
        )
        self._prev_btn = QPushButton("← 上一页")
        self._prev_btn.setFixedHeight(44)
        self._prev_btn.setStyleSheet(_nav_btn_style)
        self._prev_btn.clicked.connect(self._go_prev)
        self._prev_btn.setEnabled(False)

        self._next_btn = QPushButton("下一页 →")
        self._next_btn.setFixedHeight(44)
        self._next_btn.setStyleSheet(
            f"background:{PALETTE['accent']}; color:white;"
            "border:none; border-radius:8px; padding:8px 28px; font-size:15px;"
        )
        self._next_btn.clicked.connect(self._go_next)

        nav.addWidget(self._prev_btn)
        nav.addStretch(1)
        nav.addWidget(self._next_btn)
        right_lay.addLayout(nav)

        root.addWidget(right, 1)

    # ── word list ─────────────────────────────────────────────────────

    def _populate_word_list(self):
        self._word_list.clear()
        for w in self._words:
            n = self._seen_count(w["word"])
            text = f"{w['word']}  ×{n}" if n > 0 else w["word"]
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, w["word"])
            self._word_list.addItem(item)
        self._highlight_current_in_list()

    def _highlight_current_in_list(self):
        if not self._word:
            return
        cur_word = self._word["word"]
        for i in range(self._word_list.count()):
            item = self._word_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == cur_word:
                item.setSelected(True)
                self._word_list.scrollToItem(item)
            else:
                item.setSelected(False)

    def _update_list_count(self, word_str: str):
        n = self._seen_count(word_str)
        for i in range(self._word_list.count()):
            item = self._word_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == word_str:
                text = f"{word_str}  ×{n}" if n > 0 else word_str
                item.setText(text)
                return

    def _on_list_click(self, item: QListWidgetItem):
        word_str = item.data(Qt.ItemDataRole.UserRole)
        for w in self._words:
            if w["word"] == word_str:
                # update sequential index to match
                if self._sequential:
                    self._word_index = self._words.index(w)
                self._word = w
                self._rebuild_pages()
                self._reset_nav()
                self._highlight_current_in_list()
                return

    # ── page builders ─────────────────────────────────────────────────

    def _card(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background:white; border-radius:16px;")
        return w

    def _rebuild_pages(self):
        # Clear existing pages
        while self._stack.count():
            widget = self._stack.widget(0)
            self._stack.removeWidget(widget)
            widget.deleteLater()

        if self._word:
            self._stack.addWidget(self._make_page1())
            self._stack.addWidget(self._make_page2())
            self._stack.addWidget(self._make_page3())
        else:
            no_word = QLabel("未找到单词文件，请检查 data/words.json")
            no_word.setAlignment(Qt.AlignmentFlag.AlignCenter)
            no_word.setStyleSheet("font-size:20px;")
            self._stack.addWidget(no_word)

    def _make_page1(self) -> QWidget:
        w = self._card()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(60, 50, 60, 50)
        lay.setSpacing(20)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        word_lbl = QLabel(self._word["word"])
        f = QFont()
        f.setPointSize(52)
        f.setBold(True)
        word_lbl.setFont(f)
        word_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(word_lbl)

        phonetic = QLabel(self._word.get("phonetic", ""))
        phonetic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        phonetic.setStyleSheet(f"font-size:20px; color:{PALETTE['text_sub']};")
        lay.addWidget(phonetic)

        lay.addSpacing(20)

        en_def = QLabel(self._word.get("en_def", ""))
        en_def.setAlignment(Qt.AlignmentFlag.AlignCenter)
        en_def.setWordWrap(True)
        en_def.setStyleSheet("font-size:18px;")
        lay.addWidget(en_def)

        zh_def = QLabel(self._word.get("zh_def", ""))
        zh_def.setAlignment(Qt.AlignmentFlag.AlignCenter)
        zh_def.setWordWrap(True)
        zh_def.setStyleSheet(
            f"font-size:22px; font-weight:bold; color:{PALETTE['accent']};"
        )
        lay.addWidget(zh_def)

        lay.addStretch()
        return w

    def _make_page2(self) -> QWidget:
        w = self._card()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(60, 40, 60, 40)
        lay.setSpacing(24)

        title = QLabel(f"  {self._word['word']}  —  例句")
        f = QFont()
        f.setPointSize(18)
        f.setBold(True)
        title.setFont(f)
        lay.addWidget(title)

        for sent in self._word.get("sentences", []):
            en = QLabel(sent.get("en", ""))
            en.setWordWrap(True)
            en.setStyleSheet("font-size:17px;")
            lay.addWidget(en)

            zh = QLabel(sent.get("zh", ""))
            zh.setWordWrap(True)
            zh.setStyleSheet(
                f"font-size:15px; color:{PALETTE['text_sub']}; margin-bottom:8px;"
            )
            lay.addWidget(zh)

        lay.addStretch()
        return w

    def _make_page3(self) -> QWidget:
        w = self._card()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(60, 50, 60, 50)
        lay.setSpacing(20)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        prompt = QLabel("请拼写这个单词：")
        prompt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        prompt.setStyleSheet("font-size:20px;")
        lay.addWidget(prompt)

        self._spell_input = QLineEdit()
        self._spell_input.setPlaceholderText("输入单词后点击下一页...")
        self._spell_input.setFixedHeight(52)
        self._spell_input.setStyleSheet(
            "font-size:24px; border:2px solid #ccc; border-radius:8px; padding:4px 16px;"
        )
        self._spell_input.textChanged.connect(self._check_spelling)
        lay.addWidget(self._spell_input)

        self._spell_hint = QLabel("")
        self._spell_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._spell_hint.setStyleSheet("font-size:16px;")
        lay.addWidget(self._spell_hint)

        lay.addStretch()
        return w

    # ── navigation ────────────────────────────────────────────────────

    def _reset_nav(self):
        self._stack.setCurrentIndex(0)
        self._prev_btn.setEnabled(False)
        self._next_btn.setText("下一页 →")
        self._next_btn.setEnabled(True)
        # reconnect in case it was rewired
        try:
            self._next_btn.clicked.disconnect()
        except RuntimeError:
            pass
        self._next_btn.clicked.connect(self._go_next)

    def _go_next(self):
        cur   = self._stack.currentIndex()
        total = self._stack.count()
        if cur == total - 1:
            # last page: check spelling
            if self._word and hasattr(self, "_spell_input"):
                typed   = self._spell_input.text().strip().lower()
                correct = self._word["word"].lower()
                self._current_correct = (typed == correct)
                if not self._current_correct:
                    self._spell_hint.setText(
                        f"拼写有误，正确答案是：{self._word['word']}"
                    )
                    self._spell_hint.setStyleSheet("font-size:16px; color:#E53935;")
                    self._next_btn.setText("知道了，继续 →")
                    try:
                        self._next_btn.clicked.disconnect()
                    except RuntimeError:
                        pass
                    self._next_btn.clicked.connect(self._finish_word)
                    return
            self._finish_word()
        else:
            self._stack.setCurrentIndex(cur + 1)
            self._prev_btn.setEnabled(True)
            if cur + 1 == total - 1:
                self._next_btn.setText("完成 ✓")

    def _go_prev(self):
        cur = self._stack.currentIndex()
        if cur > 0:
            self._stack.setCurrentIndex(cur - 1)
            self._next_btn.setText("下一页 →")
            # reconnect next in case it was rewired to _finish_word
            try:
                self._next_btn.clicked.disconnect()
            except RuntimeError:
                pass
            self._next_btn.clicked.connect(self._go_next)
        if cur - 1 == 0:
            self._prev_btn.setEnabled(False)

    def _finish_word(self):
        """Called when the user completes the current word flow."""
        word_str = self._word["word"] if self._word else ""

        # persist progress
        if self._store and word_str:
            self._store.record_word_seen(word_str, self._current_correct)
            self._update_list_count(word_str)

        # light up end button (long-press was always active; normal click now works too)
        self._word_done = True
        self._end_btn.setText("结束")
        self._end_btn.setStyleSheet(self._end_btn_style_active())

        # offer next word
        self._next_btn.setText("下一个单词 →")
        try:
            self._next_btn.clicked.disconnect()
        except RuntimeError:
            pass
        self._next_btn.clicked.connect(self._load_next_word)

    def _load_next_word(self):
        self._word = self._pick_next_word(advance=True)
        self._current_correct = False
        self._rebuild_pages()
        self._reset_nav()
        self._highlight_current_in_list()

    def _check_spelling(self, text: str):
        if not self._word:
            return
        correct = self._word["word"].lower()
        if text.lower() == correct:
            self._spell_hint.setText("✓ 拼写正确！")
            self._spell_hint.setStyleSheet(
                "font-size:16px; color:#388E3C; font-weight:bold;"
            )
        else:
            self._spell_hint.setText("")

    # ── order toggle ──────────────────────────────────────────────────

    def _toggle_order(self):
        self._sequential = not self._sequential
        if self._sequential:
            # sync index to current word
            if self._word:
                try:
                    self._word_index = self._words.index(self._word)
                except ValueError:
                    self._word_index = 0
            self._order_btn.setText("顺序 ↕")
        else:
            self._order_btn.setText("随机 ⚄")

    # ── end button styles ─────────────────────────────────────────────

    @staticmethod
    def _end_btn_style_inactive() -> str:
        return (
            f"background:{PALETTE['surface2']}; color:{PALETTE['text_sub']};"
            "border:1px solid #ccc; border-radius:6px; padding:6px 14px; font-size:13px;"
        )

    @staticmethod
    def _end_btn_style_active() -> str:
        return (
            f"background:{PALETTE['accent']}; color:white;"
            "border:none; border-radius:6px; padding:6px 14px; font-size:13px;"
        )

    # ── end button (long-press always works; normal click only after word done) ─

    def _end_press(self):
        self._force_timer.start()

    def _end_release(self):
        if self._force_timer.isActive():
            self._force_timer.stop()
            # Normal click: only close if user has finished at least one word
            if self._word_done:
                self._do_close()
        # If timer already fired (_do_close was called), do nothing here

    # ── close ─────────────────────────────────────────────────────────

    def _do_close(self):
        self.hide()
        self.closed.emit()
