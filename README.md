# IPTV-Check
一款强大的IPTV直播源批量检测工具(Python/Tkinter)。支持多线程、深度检测、速度测试，并能将有效和无效源分别导出。


# 电视直播源检测工具 (IPTV Stream Checker)

![Python](https://img.shields.io/badge/Python-3.7+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

一款基于 Python 和 Tkinter (ttkbootstrap) 开发的图形化IPTV直播源有效性检测工具。它可以帮助您快速、批量地验证您的 `.m3u` 或 `.txt` 格式的直播源列表，并筛选出有效和无效的链接。

---

### 功能特性

* **图形化界面**: 使用 `ttkbootstrap` 库，提供现代化、美观的用户界面，并支持明/暗主题一键切换。
* **文件支持**: 可直接导入 `.m3u` 和 `.txt` 格式的直播源文件。
* **多线程检测**: 利用 `ThreadPoolExecutor` 实现高并发检测，大幅提升检测效率。
* **多种检测模式**:
    * **深度检测**: 不仅检查链接是否可访问，还会尝试读取数据流的头部信息，确保是有效的视频流。
    * **速度测试**: （可选，较慢）在深度检测的基础上，测试直播源的下载速度，帮助您筛选高质量的源。
* **强大的结果展示**:
    * **分类视图**: 将“全部”、“有效源”、“无效源”分在不同标签页中展示，一目了然。
    * **详细信息**: 显示每个源的频道名称、URL、状态、延迟(ms)、速度(KB/s)和备注信息。
    * **灵活排序**: 支持点击任意列标题进行升序或降序排序。
* **便捷的操作**:
    * **批量复制**: 支持使用 `Ctrl/Shift` 多选，并通过右键菜单批量复制 URL、频道名称或整行数据。
    * **快捷键**: 支持 `Ctrl+A` 全选列表中的所有项目。
* **结果导出**:
    * 一键将“有效源”导出为可直接播放的 `.m3u` 文件。
    * 将“无效源”导出为 `.txt` 文件，方便后续处理。
    * 导出的文件会自动以源文件名命名，并保存在指定目录。

---

### 程序截图
![image](https://github.com/user-attachments/assets/0dcb441f-a76a-4338-9d70-5ee81e444ca4)


---

### 如何使用

#### 1. 准备环境

本程序依赖以下 Python 库，请先通过 pip 安装它们：

```bash
pip install ttkbootstrap
pip install requests
```

#### 2. 打包exe文件（自选）
#### 下载依赖
```bash
pip install pyinstaller
```
#### 开始打包
```bash
pyinstaller --name "IPTV-Check" --onefile --windowed --add-data "assets;assets" --icon="assets/icon.ico" IPTV-Check.py
```
