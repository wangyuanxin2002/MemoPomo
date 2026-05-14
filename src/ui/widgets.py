"""
Shared custom widgets used across multiple UI files.
"""

import re

from PyQt6.QtWidgets import QTextEdit, QPlainTextEdit
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent, QTextCursor


# Matches list prefixes: "1. " / "1, " / "1、" / "1，" / "1 " (number + separator + optional space)
_LIST_RE = re.compile(r'^(\d+)[.,、，]\s*|^(\d+)\s+')

# Matches a normalised stored prefix "N. " (what we always write out)
_STORED_RE = re.compile(r'^(\d+)\.\s')


def _match_list_line(text: str):
    """Return (number, prefix_len) if text starts with a list prefix, else None."""
    m = _LIST_RE.match(text)
    if not m:
        return None
    num = int(m.group(1) or m.group(2))
    return num, m.end()


def _renumber_from(widget, start_block_num: int, start_list_num: int):
    """
    Walk forward from the block at position start_block_num and renumber
    consecutive list lines starting at start_list_num.
    Stops at the first non-list line.
    """
    doc = widget.document()
    block = doc.findBlockByNumber(start_block_num)
    expected = start_list_num
    cursor = widget.textCursor()

    while block.isValid():
        text = block.text()
        m = _STORED_RE.match(text)
        if not m:
            break
        current_num = int(m.group(1))
        if current_num != expected:
            # Replace the number prefix
            old_prefix = m.group(0)          # e.g. "2. "
            new_prefix = f"{expected}. "
            c = QTextCursor(block)
            c.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            for _ in range(len(old_prefix)):
                c.deleteChar()
            c.insertText(new_prefix)
        expected += 1
        block = block.next()

    widget.setTextCursor(cursor)  # restore original cursor


def _auto_list_key_press(widget, ev: QKeyEvent) -> bool:
    """
    Shared auto-numbered-list logic for QTextEdit / QPlainTextEdit.
    Returns True if the event was handled (caller should NOT call super()).

    Triggers:
      - "1. " / "1, " / "1、" / "1，" / "1 " at line start → list mode
    Enter behaviour:
      - Non-empty list line → insert next number, renumber all following lines
      - Empty list line (just the prefix) → remove prefix, exit list mode
    Backspace:
      - Caret right after "N. " prefix → remove entire prefix
    """
    key = ev.key()
    cursor = widget.textCursor()
    block_text = cursor.block().text()
    pos_in_block = cursor.positionInBlock()

    # ── Enter / Return ──────────────────────────────────────────────────
    if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
        result = _match_list_line(block_text)
        if result:
            num, prefix_len = result
            content = block_text[prefix_len:]

            if content.strip() == "":
                # Empty item → strip prefix and exit list
                cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
                cursor.removeSelectedText()
                cursor.insertBlock()
                widget.setTextCursor(cursor)
                return True
            else:
                # Normalise current line prefix to "N. " form
                current_block_num = cursor.block().blockNumber()
                stored = f"{num}. "
                if block_text[:prefix_len] != stored:
                    c2 = QTextCursor(cursor.block())
                    c2.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                    for _ in range(prefix_len):
                        c2.deleteChar()
                    c2.insertText(stored)
                    cursor = widget.textCursor()
                    pos_in_block += len(stored) - prefix_len  # adjust after normalise

                # Text after the caret goes to the new line
                next_num = num + 1
                next_prefix = f"{next_num}. "

                # Select from caret to end of block (the "tail" to move down)
                cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock,
                                    QTextCursor.MoveMode.KeepAnchor)
                tail = cursor.selectedText()
                cursor.removeSelectedText()   # delete tail from current line

                # Insert new block with next prefix + tail
                cursor.insertBlock()
                cursor.insertText(next_prefix + tail)

                # Place caret right after the new prefix (before tail)
                cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                cursor.movePosition(QTextCursor.MoveOperation.Right,
                                    QTextCursor.MoveMode.MoveAnchor,
                                    len(next_prefix))
                widget.setTextCursor(cursor)

                # Renumber all following list lines
                _renumber_from(widget, current_block_num + 2, next_num + 1)
                return True

    # ── Backspace ───────────────────────────────────────────────────────
    if key == Qt.Key.Key_Backspace:
        result = _match_list_line(block_text)
        if result:
            _, prefix_len = result
            if pos_in_block == prefix_len:
                cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                for _ in range(prefix_len):
                    cursor.deleteChar()
                widget.setTextCursor(cursor)
                return True

    return False


class AutoListTextEdit(QTextEdit):
    """QTextEdit with automatic ordered-list continuation."""

    def keyPressEvent(self, ev: QKeyEvent):
        if not _auto_list_key_press(self, ev):
            super().keyPressEvent(ev)


class AutoListPlainTextEdit(QPlainTextEdit):
    """QPlainTextEdit with automatic ordered-list continuation."""

    def keyPressEvent(self, ev: QKeyEvent):
        if not _auto_list_key_press(self, ev):
            super().keyPressEvent(ev)
