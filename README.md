# 🍅 MemoPomo · 备忘番茄

<p align="left">
  <img src="https://img.shields.io/badge/Python-3.10+-blue.svg" alt="Python Version">
  <img src="https://img.shields.io/badge/PyQt6-Framework-green.svg" alt="PyQt6">
  <img src="https://img.shields.io/badge/Platform-Windows_Only-lightgrey.svg" alt="Windows Only">
  <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License">
</p>

> **"想"与"做"，只差一个番茄钟的距离。**

MemoPomo 是一款专为 Windows 打造的轻量级、纯本地工作流桌面工具。它将**四象限备忘录**、**周历 / 日历时间块排期**与**番茄钟专注**融为一体，让你从记录想法到完成任务一气呵成。

---

## ✨ 核心功能

### 📋 四象限备忘录
- 按「重要 × 紧急」四象限管理任务
- 双击卡片编辑标题和备注
- 拖拽卡片在象限间移动
- 点击 ✓ 标记完成（完成任务自动沉底并显示删除线）
- 右键设置**定时重复任务**（每天 / 每周 / 每月），自动在日历生成对应时间块
- 删除备忘任务会级联删除所有关联的日历时间块

### 📅 可视化日历（Timeboxing）
- 周视图 / 日视图 / 月视图切换
- 在空白区域点击即可新建时间块，开始时间自动对齐到最近的 15 分钟
- 拖拽时间块移动或调整时长
- 将备忘卡片拖入日历，自动创建一小时计划块
- 到达时间块开始时间时全屏弹窗提醒，支持**立即启动番茄钟**或**推迟 N 分钟**

### 🍅 番茄钟
- 自由定制工作段 + 休息段模板（如 25+5、50+10）
- 支持关联备忘任务，完成后自动计入日历
- 倒计时中折叠为**极简悬浮窗**，不遮挡屏幕
- 悬浮窗支持暂停 / 继续 / 跳过 / 重置 / 返回主界面
- 每个阶段（包括最后一段）结束后弹出**全屏背单词提醒**

### 📖 背单词
- 每段番茄钟结束后自动弹出，也可随时点击「开始背单词」独立使用
- 三步交互：看释义猜单词 → 填写拼写 → 查看结果
- 左侧单词列表显示每个单词的学习次数，可点击直接跳转
- 顺序 / 随机模式一键切换
- 背完当前单词后「结束」按钮亮起，可继续背下一个或退出

### ⚙️ 其他
- 四象限颜色、番茄钟模板、默认推迟时长均可在设置中自定义
- 所有数据本地 JSON 存储，无需联网，无账号

---

## 🛠️ 技术栈

| 项目 | 版本 |
|------|------|
| Python | 3.10+ |
| GUI 框架 | PyQt6 |
| 数据存储 | 本地 JSON |
| 平台 | Windows only |

---

## 🚀 快速开始

### 1. 克隆仓库
```bash
git clone https://github.com/wangyuanxin2002/MemoPomo.git
cd MemoPomo
```

### 2. 安装依赖
```bash
pip install PyQt6
```

### 3. 运行
```bash
python main.py
```

---

## 📁 项目结构

```
MemoPomo/
├── main.py                  # 入口
├── data/
│   ├── words.json           # 背单词词库
│   └── templates.json       # 番茄钟模板（首次运行自动生成）
└── src/
    ├── core/
    │   ├── engine.py        # 番茄钟计时引擎
    │   ├── models.py        # 数据模型
    │   └── store.py         # 持久化存储
    └── ui/
        ├── main_window.py   # 主窗口
        ├── calendar_widget.py
        ├── memo_widget.py
        ├── pomodoro_widget.py
        ├── word_alert.py    # 背单词全屏提醒
        ├── floaty_window.py # 悬浮窗
        ├── settings_dialog.py
        └── theme.py
```

---

## 📄 License

MIT
