# MemoPomo
一款极简的本地工作流工具：四象限备忘录 + 拖拽式排期 + 番茄钟专注。

A lightweight, offline-first Windows productivity tool integrating Pomodoro, Eisenhower Matrix, and Timeboxing calendar. 

# 🍅 MemoPomo (备忘番茄)

<p align="left">
  <img src="https://img.shields.io/badge/Python-3.9+-blue.svg" alt="Python Version">
  <img src="https://img.shields.io/badge/PyQt6-Framework-green.svg" alt="PyQt6">
  <img src="https://img.shields.io/badge/Platform-Windows_Only-lightgrey.svg" alt="Windows Only">
  <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License">
</p>

> **“想”与“做”，只差一个番茄钟的距离。**

MemoPomo 是一款专为 Windows 打造的轻量级、纯本地工作流桌面工具。它将**四象限备忘录**、**周历时间块排期**与**番茄钟专注**完美融合。拒绝复杂的功能堆砌，没有云端同步的隐私焦虑，让你把每一项任务都落地为具体的行动。

---

## ✨ 核心特色

- 🎯 **从备忘到专注的无缝衔接**：在四宫格记录灵感和任务 -> 拖拽到日历成为计划 -> 点击任务直接开启番茄钟，一气呵成。
- 🍅 **沉浸式番茄钟体验**：
  - 自由定制工作与休息时间模板（如 `25+5` 或 `50+10`）。
  - 计时开始后自动折叠为极简悬浮窗，不干扰主屏幕。
  - 段落结束提供全屏强制提醒（支持打开网页或本地音乐）。
- 📅 **可视化周历（Timeboxing）**：将任务转化为时间块（Time Blocks），直观展示已完成的努力和未来的规划。
- 🔒 **纯本地、极轻量**：无须联网，无须账号注册。所有数据以轻量级 JSON 格式安全保存在本地，极速启动，不吃内存。

---

## 📸 界面预览
*(提示：开发完成后，请将你的软件截图命名为 `main.png` 和 `floating.png` 放到仓库的 `assets` 文件夹下，替换下方链接)*

*图片占位：主界面全览 (包含日历、番茄钟、备忘录)*
<!-- ![Main Interface](assets/main.png) -->

*图片占位：极简倒计时悬浮窗*
<!-- ![Floating Window](assets/floating.png) -->

---

## 🛠️ 技术栈

- **语言**: Python 3.9+
- **GUI 框架**: PyQt6
- **数据存储**: 本地 JSON

本软件目前仅支持 Windows 平台。

---

## 🚀 快速开始

如果你想在本地运行或参与开发 MemoPomo：

### 1. 克隆仓库
```bash
git clone [https://github.com/YourUsername/MemoPomo.git](https://github.com/YourUsername/MemoPomo.git)
cd MemoPomo
