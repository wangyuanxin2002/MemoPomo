"""
Settings dialog: alert modes, startup, template editor, snooze default.
"""

import winreg
import sys
from PyQt6.QtWidgets import (
    QDialog, QTabWidget, QWidget, QFormLayout, QVBoxLayout,
    QHBoxLayout, QCheckBox, QLineEdit, QPushButton,
    QSpinBox, QLabel, QDialogButtonBox, QFileDialog,
    QListWidget, QListWidgetItem, QInputDialog, QMessageBox,
    QColorDialog,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from src.core.models import AppSettings, PomodoroTemplate
from src.core.store import Store

STARTUP_KEY  = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME     = "PomodoroFocus"


def _set_startup(enable: bool):
    exe = sys.executable if getattr(sys, "frozen", False) else sys.argv[0]
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_KEY,
                             0, winreg.KEY_SET_VALUE)
        if enable:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f'"{exe}"')
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception:
        pass


class SettingsDialog(QDialog):
    def __init__(self, store: Store, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumWidth(440)
        self._store = store
        s = store.settings

        root = QVBoxLayout(self)
        tabs = QTabWidget()
        root.addWidget(tabs)

        # ---------- Tab: General ----------
        gen = QWidget()
        gf  = QFormLayout(gen)

        self._startup_cb = QCheckBox("开机自动启动")
        self._startup_cb.setChecked(s.startup_with_windows)
        gf.addRow(self._startup_cb)

        self._snooze_spin = QSpinBox()
        self._snooze_spin.setRange(1, 120)
        self._snooze_spin.setValue(s.snooze_minutes)
        self._snooze_spin.setSuffix(" 分钟")
        gf.addRow("默认推迟时长", self._snooze_spin)

        tabs.addTab(gen, "常规")

        # ---------- Tab: Alert ----------
        alert_tab = QWidget()
        af = QFormLayout(alert_tab)
        a  = s.alert

        self._rest_cb = QCheckBox("显示休息提示全屏页")
        self._rest_cb.setChecked(a.mode_rest_screen)
        af.addRow(self._rest_cb)

        self._url_cb = QCheckBox("自动打开网页")
        self._url_cb.setChecked(a.mode_open_url)
        self._url_edit = QLineEdit(a.url)
        self._url_edit.setPlaceholderText("https://...")
        af.addRow(self._url_cb)
        af.addRow("网址", self._url_edit)

        self._file_cb = QCheckBox("自动打开文件")
        self._file_cb.setChecked(a.mode_open_file)
        file_row = QHBoxLayout()
        self._file_edit = QLineEdit(a.file_path)
        browse_btn = QPushButton("浏览…")
        browse_btn.clicked.connect(self._browse_file)
        file_row.addWidget(self._file_edit)
        file_row.addWidget(browse_btn)
        af.addRow(self._file_cb)
        af.addRow("文件路径", file_row)

        tabs.addTab(alert_tab, "提醒")

        # ---------- Tab: Template ----------
        tpl_tab = QWidget()
        tl = QVBoxLayout(tpl_tab)
        tl.addWidget(QLabel("番茄钟模板（分钟，用逗号分隔工作段和休息段）"))
        tl.addWidget(QLabel("格式示例：25w,5b,25w,5b,25w,15b  (w=工作 b=休息)"))

        self._tpl_edit = QLineEdit()
        tpl = store.default_template()
        parts = []
        for seg in tpl.segments:
            suffix = "b" if seg["is_break"] else "w"
            parts.append(f"{seg['duration_min']}{suffix}")
        self._tpl_edit.setText(",".join(parts))
        tl.addWidget(self._tpl_edit)
        tl.addStretch()

        tabs.addTab(tpl_tab, "模板")

        # ---------- Tab: Quadrant Colors ----------
        qc_tab = QWidget()
        qc_lay = QVBoxLayout(qc_tab)
        qc_lay.addWidget(QLabel("备忘录四象限颜色（点击色块修改）"))

        _q_labels = ["Q1 重要且紧急", "Q2 重要不紧急", "Q3 紧急不重要", "Q4 不重要不紧急"]
        self._q_color_btns: list[QPushButton] = []
        for i, lbl in enumerate(_q_labels):
            row = QHBoxLayout()
            row.addWidget(QLabel(lbl), 1)
            btn = QPushButton()
            btn.setFixedSize(60, 26)
            color = s.quadrant_colors[i]
            btn.setStyleSheet(f"background:{color}; border:1px solid #999; border-radius:4px;")
            btn.clicked.connect(lambda _, idx=i: self._pick_q_color(idx))
            self._q_color_btns.append(btn)
            row.addWidget(btn)
            qc_lay.addLayout(row)
        qc_lay.addStretch()
        tabs.addTab(qc_tab, "象限颜色")

        # ---------- OK / Cancel ----------
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._apply)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择文件")
        if path:
            self._file_edit.setText(path)

    def _pick_q_color(self, idx: int):
        current = self._store.settings.quadrant_colors[idx]
        color = QColorDialog.getColor(QColor(current), self, f"选择 Q{idx+1} 颜色")
        if color.isValid():
            hex_color = color.name()
            self._store.settings.quadrant_colors[idx] = hex_color
            self._q_color_btns[idx].setStyleSheet(
                f"background:{hex_color}; border:1px solid #999; border-radius:4px;"
            )

    def _apply(self):
        s = self._store.settings
        s.startup_with_windows = self._startup_cb.isChecked()
        s.snooze_minutes       = self._snooze_spin.value()
        s.alert.mode_rest_screen = self._rest_cb.isChecked()
        s.alert.mode_open_url    = self._url_cb.isChecked()
        s.alert.url              = self._url_edit.text().strip()
        s.alert.mode_open_file   = self._file_cb.isChecked()
        s.alert.file_path        = self._file_edit.text().strip()
        _set_startup(s.startup_with_windows)

        # parse template
        raw = self._tpl_edit.text().strip()
        segs = []
        for tok in raw.split(","):
            tok = tok.strip()
            if not tok:
                continue
            is_break = tok.endswith("b")
            try:
                mins = int(tok.rstrip("wb"))
                segs.append({"duration_min": mins, "is_break": is_break})
            except ValueError:
                QMessageBox.warning(self, "格式错误",
                                    f"无法解析：{tok}\n格式应为数字后跟 w 或 b，例如 25w")
                return

        if segs:
            tpl = self._store.default_template()
            tpl.segments = segs
            self._store.save_templates()

        self._store.save_settings()
        self.accept()
