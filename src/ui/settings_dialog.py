"""
Settings dialog: alert modes, startup, template editor, snooze default.
"""

import winreg
import sys
import json
import shutil
import zipfile
import tempfile
from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QTabWidget, QWidget, QFormLayout, QVBoxLayout,
    QHBoxLayout, QCheckBox, QLineEdit, QPushButton,
    QSpinBox, QLabel, QDialogButtonBox, QFileDialog,
    QListWidget, QListWidgetItem, QInputDialog, QMessageBox,
    QColorDialog, QScrollArea, QFrame,
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

        # ---------- Tab: Calendar Layout ----------
        cal_tab = QWidget()
        cal_lay = QFormLayout(cal_tab)

        self._cal_hour_h = QSpinBox()
        self._cal_hour_h.setRange(30, 200)
        self._cal_hour_h.setValue(getattr(s, "cal_hour_h", 64))
        self._cal_hour_h.setSuffix(" px / 小时")
        cal_lay.addRow("时间格高度（密度）", self._cal_hour_h)

        self._cal_start_h = QSpinBox()
        self._cal_start_h.setRange(0, 23)
        self._cal_start_h.setValue(getattr(s, "cal_start_h", 0))
        self._cal_start_h.setSuffix(" 时")
        cal_lay.addRow("显示起始时间", self._cal_start_h)

        self._cal_end_h = QSpinBox()
        self._cal_end_h.setRange(1, 24)
        self._cal_end_h.setValue(getattr(s, "cal_end_h", 24))
        self._cal_end_h.setSuffix(" 时")
        cal_lay.addRow("显示终止时间", self._cal_end_h)

        self._cal_day_w = QSpinBox()
        self._cal_day_w.setRange(60, 400)
        self._cal_day_w.setValue(getattr(s, "cal_day_w", 120))
        self._cal_day_w.setSuffix(" px / 天")
        cal_lay.addRow("周视图列宽", self._cal_day_w)

        tabs.addTab(cal_tab, "日历布局")

        # ---------- Tab: Data ----------
        data_tab = QWidget()
        data_lay = QVBoxLayout(data_tab)
        data_lay.setSpacing(12)
        data_lay.addWidget(QLabel("导出：将设置、日历、备忘录、番茄记录、单词进度打包为 .zip"))
        export_btn = QPushButton("📦  导出所有数据…")
        export_btn.clicked.connect(self._export_data)
        data_lay.addWidget(export_btn)
        data_lay.addSpacing(8)
        data_lay.addWidget(QLabel("导入：从之前导出的 .zip 还原所有数据（当前数据会被覆盖）"))
        import_btn = QPushButton("📂  导入所有数据…")
        import_btn.clicked.connect(self._import_data)
        data_lay.addWidget(import_btn)
        data_lay.addStretch()
        tabs.addTab(data_tab, "数据")

        # ---------- Tab: Deleted Tasks ----------
        trash_tab = QWidget()
        trash_lay = QVBoxLayout(trash_tab)
        trash_lay.setSpacing(8)

        trash_header = QHBoxLayout()
        trash_header.addWidget(QLabel("已删除的备忘录任务（可恢复或彻底删除）"), 1)
        clear_all_btn = QPushButton("清空回收站")
        clear_all_btn.clicked.connect(self._clear_all_deleted)
        trash_header.addWidget(clear_all_btn)
        trash_lay.addLayout(trash_header)

        self._trash_scroll_area = QScrollArea()
        self._trash_scroll_area.setWidgetResizable(True)
        self._trash_scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self._trash_container = QWidget()
        self._trash_list_lay = QVBoxLayout(self._trash_container)
        self._trash_list_lay.setSpacing(4)
        self._trash_list_lay.setContentsMargins(0, 0, 0, 0)
        self._trash_list_lay.addStretch()
        self._trash_scroll_area.setWidget(self._trash_container)
        trash_lay.addWidget(self._trash_scroll_area, 1)

        tabs.addTab(trash_tab, "回收站")
        tabs.currentChanged.connect(self._on_tab_changed)
        self._trash_tab_index = tabs.count() - 1

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

    def _export_data(self):
        dst, _ = QFileDialog.getSaveFileName(
            self, "导出数据", "MemoPomo-backup.zip", "ZIP 文件 (*.zip)"
        )
        if not dst:
            return
        from src.core.store import DATA_DIR
        files = [
            "settings.json", "memo.json", "calendar.json",
            "pomodoro.json", "templates.json",
            "word_progress.json", "words.json", "sticky.json",
        ]
        try:
            with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zf:
                for name in files:
                    p = DATA_DIR / name
                    if p.exists():
                        zf.write(str(p), name)
            QMessageBox.information(self, "导出完成", f"数据已保存到：\n{dst}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))

    def _import_data(self):
        src, _ = QFileDialog.getOpenFileName(
            self, "导入数据", "", "ZIP 文件 (*.zip)"
        )
        if not src:
            return
        ret = QMessageBox.warning(
            self, "确认导入",
            "导入将覆盖当前所有数据，操作不可撤销。\n确定继续吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        from src.core.store import DATA_DIR
        try:
            with zipfile.ZipFile(src, "r") as zf:
                zf.extractall(str(DATA_DIR))
            self._store.load_all()
            QMessageBox.information(self, "导入完成", "数据已还原，请重启软件以刷新界面。")
        except Exception as e:
            QMessageBox.critical(self, "导入失败", str(e))

    def _on_tab_changed(self, index: int):
        if index == self._trash_tab_index:
            self._refresh_trash()

    def _refresh_trash(self):
        # remove all rows except the trailing stretch
        while self._trash_list_lay.count() > 1:
            item = self._trash_list_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        deleted = [t for t in self._store.memo_tasks if t.deleted]
        if not deleted:
            lbl = QLabel("暂无已删除的任务")
            lbl.setStyleSheet("color:#aaa; padding:12px;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._trash_list_lay.insertWidget(0, lbl)
            return

        from src.core.models import QUADRANTS
        for task in deleted:
            row = QFrame()
            row.setFrameShape(QFrame.Shape.StyledPanel)
            row.setStyleSheet("QFrame{background:#f8f8f8; border:1px solid #e0e0e0; border-radius:6px;}")
            row_lay = QHBoxLayout(row)
            row_lay.setContentsMargins(8, 6, 8, 6)
            row_lay.setSpacing(8)

            q_label = QUADRANTS.get(task.quadrant, f"Q{task.quadrant}")
            date_str = ""
            if task.created_at:
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(task.created_at)
                    date_str = f"  {dt.month}.{dt.day}"
                except Exception:
                    pass

            info = QLabel(f"[{q_label}]  {task.title}{date_str}")
            info.setStyleSheet("font-size:13px;")
            info.setWordWrap(False)
            row_lay.addWidget(info, 1)

            restore_btn = QPushButton("恢复")
            restore_btn.setFixedWidth(52)
            restore_btn.setStyleSheet(
                "background:#4CAF50; color:white; border:none; border-radius:4px; padding:3px 6px;"
            )
            restore_btn.clicked.connect(lambda _, tid=task.id: self._restore_task(tid))
            row_lay.addWidget(restore_btn)

            del_btn = QPushButton("彻底删除")
            del_btn.setFixedWidth(68)
            del_btn.setStyleSheet(
                "background:#EF5350; color:white; border:none; border-radius:4px; padding:3px 6px;"
            )
            del_btn.clicked.connect(lambda _, tid=task.id: self._hard_delete_task(tid))
            row_lay.addWidget(del_btn)

            self._trash_list_lay.insertWidget(self._trash_list_lay.count() - 1, row)

    def _restore_task(self, task_id: str):
        self._store.restore_memo(task_id)
        self._refresh_trash()

    def _hard_delete_task(self, task_id: str):
        self._store.hard_delete_memo(task_id)
        self._refresh_trash()

    def _clear_all_deleted(self):
        deleted = [t for t in self._store.memo_tasks if t.deleted]
        if not deleted:
            return
        ret = QMessageBox.warning(
            self, "确认清空",
            f"将彻底删除 {len(deleted)} 条任务，操作不可撤销。\n确定继续吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        for task in deleted:
            self._store.hard_delete_memo(task.id)
        self._refresh_trash()

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

        # calendar layout
        start_h = self._cal_start_h.value()
        end_h   = self._cal_end_h.value()
        if end_h <= start_h:
            QMessageBox.warning(self, "时间范围错误",
                                "终止时间必须大于起始时间。")
            return
        s.cal_hour_h  = self._cal_hour_h.value()
        s.cal_start_h = start_h
        s.cal_end_h   = end_h
        s.cal_day_w   = self._cal_day_w.value()

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
