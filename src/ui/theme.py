"""
Shared stylesheet and color palette (light theme).
"""

PALETTE = {
    "bg":           "#F5F5F5",
    "surface":      "#FFFFFF",
    "surface2":     "#EFEFEF",
    "border":       "#D0D0D0",
    "accent":       "#4A90D9",
    "accent_light": "#EAF3FC",
    "text":         "#1A1A1A",
    "text_sub":     "#666666",
    "work_block":   "#1565C0",
    "plan_block":   "#A8C8F0",
    "break_block":  "#66BB6A",
    "q1":           "#FFEBEE",   # 重要且紧急   – 淡红
    "q2":           "#E8F5E9",   # 重要不紧急   – 淡绿
    "q3":           "#FFF8E1",   # 紧急不重要   – 淡黄
    "q4":           "#F3E5F5",   # 不重要不紧急 – 淡紫
    "q1_header":    "#EF9A9A",
    "q2_header":    "#A5D6A7",
    "q3_header":    "#FFE082",
    "q4_header":    "#CE93D8",
}

APP_STYLE = f"""
QWidget {{
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 13px;
    color: {PALETTE['text']};
    background-color: {PALETTE['bg']};
}}

QMainWindow, QDialog {{
    background-color: {PALETTE['bg']};
}}

QPushButton {{
    background-color: {PALETTE['accent']};
    color: white;
    border: none;
    border-radius: 6px;
    padding: 6px 16px;
    font-size: 13px;
}}
QPushButton:hover  {{ background-color: #3A7BC8; }}
QPushButton:pressed {{ background-color: #2E6AB5; }}
QPushButton:disabled {{ background-color: {PALETTE['border']}; color: {PALETTE['text_sub']}; }}

QPushButton[flat=true] {{
    background-color: transparent;
    color: {PALETTE['accent']};
    border: 1px solid {PALETTE['accent']};
}}
QPushButton[flat=true]:hover {{ background-color: {PALETTE['accent_light']}; }}

QLineEdit, QTextEdit, QSpinBox, QComboBox {{
    background-color: {PALETTE['surface']};
    border: 1px solid {PALETTE['border']};
    border-radius: 5px;
    padding: 4px 8px;
}}
QLineEdit:focus, QTextEdit:focus {{
    border-color: {PALETTE['accent']};
}}

QScrollBar:vertical {{
    width: 8px;
    background: {PALETTE['surface2']};
}}
QScrollBar::handle:vertical {{
    background: {PALETTE['border']};
    border-radius: 4px;
    min-height: 24px;
}}

QLabel[role=title] {{
    font-size: 16px;
    font-weight: bold;
}}
QLabel[role=subtitle] {{
    font-size: 12px;
    color: {PALETTE['text_sub']};
}}
"""
