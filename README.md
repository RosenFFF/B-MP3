<div align="center">

<img src="resources/icon.png" width="130" height="130" alt="LuminaStudio Icon" style="border-radius: 26px; box-shadow: 0 10px 25px rgba(0,0,0,0.5);" />

# 光影工坊 · LuminaStudio (B-MP3)

**极简、现代、全能的 Windows 本机音视频转码、B 站缓存智能合成与音频提取工坊**

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg?style=flat-square&logo=python)](https://www.python.org/)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-green.svg?style=flat-square)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows-0078D6.svg?style=flat-square&logo=windows)](https://www.microsoft.com/)
[![FFmpeg Inside](https://img.shields.io/badge/FFmpeg-9.0%2B-red.svg?style=flat-square&logo=ffmpeg)](https://ffmpeg.org/)

[功能特性](#-功能特性) • [快速开始](#-快速开始) • [操作说明](#-操作指南) • [独立打包](#-打包独立-exe) • [目录结构](#-项目结构) • [开源协议](#-开源协议)

</div>

---

## 📖 项目简介

日常生活中，我们经常需要处理各种视频与音频：
- **B 站客户端下载的缓存**：音频与视频被分离存储为 `video.m4s` 和 `audio.m4s`，或者切为多段 `0.flv`、`1.flv`、`.blv`，普通播放器无法播放；
- **视频转音频需求**：听播客、听音乐、提取背景音（BGM），需要将视频快速转为通用的 MP3 或无损 M4A/FLAC；
- **格式与体积转换**：微信/办公场景对视频体积限制严格，需要兼顾画质与压缩比；或者编码已适合只需秒级无损封装（Stream Copy）。

**光影工坊 (LuminaStudio / B-MP3)** 就是为此而生的轻量化桌面工具箱。纯本地运行，不上传任何数据，保护用户隐私；界面采用定制质感深色主题，支持全窗口拖放与 Windows 系统「发送到」右键集成。

---

## ✨ 功能特性

- 🎯 **B 站客户端缓存智能无损合成**
  - 自动识别同一目录下的 `video.m4s` 与 `audio.m4s` 并合并为标准 MP4；
  - 读取 `entry.json` 元数据，自动提取真实视频标题与分 P 名称作为文件名；
  - 多段式视频分片（如 `0.flv`, `1.flv`）按序号自动无缝拼接；
  - 自动剔除专有缓存头部数据，兼容嵌入同名 `.srt` / `.ass` / `.vtt` 外挂字幕。

- ⚡ **视频转码 & 秒级无损封装**
  - **快速封装**：编码兼容时采用流复制（Stream Copy），耗时数秒且**100% 保持原片画质**；
  - **标准画质**：H.264 (CRF 23) + AAC 192 kbps，平衡画质与体积；
  - **超高画质**：H.264 (CRF 18) + AAC 192 kbps，视觉无损；
  - **压缩减小**：H.264 (CRF 28)，宽度超过 1280 时自动智能等比缩放。
  - 支持输出为 **MP4**、**MKV**、**MOV** 格式（MP4/MOV 自动优化 FastStart 文件头，支持边下边播拖动）。

- 🎵 **高保真音频提取**
  - 支持从任意视频中一键剥离并输出 **MP3**、**M4A**、**WAV**、**FLAC**；
  - 若源视频音轨编码符合目标格式，自动采用无损直出。

- 📊 **视频智能总结与分镜抽帧**
  - 自动分析视频技术规格：时长、分辨率、帧率、编码、码率、文件大小、响度、分段；
  - 输出格式规整的 `总结.md` 技术报告；
  - 均匀抽帧生成精美的全景时间线分镜网格拼图 `storyboard.jpg`。

- 🖥️ **现代美学体验与系统级整合**
  - 采用深曜石暗色质感界面，配备高分辨率矢量应用图标与窗口标头；
  - 支持全窗口自由拖拽文件/文件夹批量导入；
  - 一键注入 Windows 资源管理器「发送到」菜单，右键即可直接处理。

---

## 🚀 快速开始

### 方式一：直接运行已编译的免安装版（推荐）

1. 从 Release 或构建目录中找到：
   ```text
   dist\光影工坊\光影工坊.exe
   ```
2. 直接双击打开即可使用！内部已打包包含 FFmpeg 与运行时组件，无需安装 Python 环境，随拷随用。

### 方式二：双击脚本启动（便携开发）

- **`启动光影工坊.bat`**：一键启动。若存在打包好的 `.exe` 将优先极速唤起，未打包时自动调用虚拟环境。将音视频直接拖放到该 `.bat` 上即可快速导入。
- **`安装并启动.bat`**：首次从源码运行时双击，自动创建 Python 虚拟环境、安装依赖并下载/准备 FFmpeg。

### 方式三：源码运行

需本机安装 Python 3.11 或更新版本：

```bash
# 1. 克隆代码仓库
git clone git@github.com:RosenFFF/B-MP3.git
cd B-MP3

# 2. 创建并激活虚拟环境
python -m venv .venv
.venv\Scripts\activate

# 3. 安装依赖包
pip install -r requirements.txt

# 4. 首次启动检查 FFmpeg
python -m pianzhuang.bootstrap

# 5. 启动应用
python main.py
```

---

## 🎮 操作指南

### 1. 媒体导入

| 导入入口 | 快捷键 | 说明 |
| :--- | :--- | :--- |
| **拖入文件/文件夹** | 鼠标直接拖拽 | 窗口任意位置均支持拖入单个或多个视频、文件夹或缓存目录 |
| **选择文件** | `Ctrl + O` | 打开系统文件对话框批量选择音视频 |
| **选择文件夹** | `Ctrl + Shift + O` | 递归扫描所选文件夹内的所有支持文件 |
| **粘贴路径** | `Ctrl + V` | 读取剪贴板中的本地文件/文件夹绝对路径 |
| **扫描 B 站缓存** | 界面按钮 | 自动检索系统常见 B 站客户端缓存目录 (`%LOCALAPPDATA%\bilibili` 等) |
| **添加到「发送到」** | 界面按钮 | 添加至 Windows「发送到」菜单，可在资源管理器右键视频随时导入 |

支持导入格式：
- **视频**：MP4, MKV, AVI, MOV, WMV, WEBM, FLV, TS, M4V, MPG, M4S, BLV 等
- **音频**：MP3, M4A, WAV, AAC, FLAC, OGG, OPUS 等

### 2. 输出与配置

- **默认输出路径**：系统「视频」文件夹下的 `光影工坊输出`（可在界面底部自由更改或点击“打开”浏览）。
- **用户配置路径**：`%APPDATA%\LuminaStudio\config.json`
- **运行记录日志**：`%APPDATA%\LuminaStudio\last.log`

---

## 💻 命令行接口 (CLI)

除了图形界面，程序还支持直接通过命令行进行脚本化批处理：

```bash
# 打开窗口并导入指定文件
光影工坊.exe --import "D:\videos\demo.mp4"

# 批量转码视频为标准画质 MP4
光影工坊.exe --convert "D:\videos\input.flv" -o "D:\output" --preset 标准 --container MP4

# 高音质提取视频中的音频为 M4A
光影工坊.exe --audio "D:\videos\input.mp4" --format M4A -o "D:\output"

# 生成视频技术总结与分镜拼图
光影工坊.exe --summary "D:\videos\input.mp4" -o "D:\output"
```

---

## 📦 打包独立 .EXE

本项目已配置完善的 PyInstaller 构建管线：

1. 双击项目根目录下的 **`打包光影工坊.bat`**；
2. 或者在虚拟环境中执行构建脚本：
   ```bash
   python build_exe.py
   ```
3. 构建完成后，独立的便携文件夹将生成在：
   ```text
   dist/
   └── 光影工坊/
       ├── 光影工坊.exe        # 独立运行主程序
       ├── resources/         # 定制图标与资源
       ├── vendor/bin/        # 内置 FFmpeg & FFprobe
       └── _internal/         # 依赖运行时库
   ```

---

## 📂 项目结构

```text
B-MP3/
├── resources/                # 应用图标与资源文件
│   ├── icon.ico              # Windows 多分辨率图标 (16~256px)
│   └── icon.png              # 高清透明矢量图
├── pianzhuang/               # 核心源码包
│   ├── app.py                # CustomTkinter 现代图形界面主窗口
│   ├── binaries.py           # FFmpeg / FFprobe 智能定位与下载
│   ├── bootstrap.py          # 启动引导与环境检测
│   ├── cli.py                # 命令行 CLI 入口解析
│   ├── config.py             # 配置管理与日志记录
│   ├── ingest.py             # 媒体路径扫描、B站缓存与元数据解析
│   ├── jobs.py               # 转换/提取/抽帧后台任务线程编排
│   ├── media.py              # FFprobe 解析与 FFmpeg 命令行组装
│   ├── models.py             # 数据结构与枚举定义
│   ├── report.py             # 分镜拼图与 Markdown 报告生成
│   └── sendto.py             # Windows「发送到」快捷方式注册
├── tests/                    # 单元测试用例
│   └── test_core.py          # 核心转码与功能测试
├── build_exe.py              # PyInstaller 打包构建脚本
├── app.spec                  # PyInstaller 编译规格文件
├── requirements.txt          # Python 依赖清单
├── 启动光影工坊.bat          # 便捷启动脚本
├── 安装并启动.bat            # 源码环境一键安装脚本
├── 打包光影工坊.bat          # 一键重新打包可执行程序
├── LICENSE                   # Apache 2.0 开源许可证
└── README.md                 # 项目详细说明文档
```

---

## 📄 开源协议

本项目基于 [Apache License 2.0](LICENSE) 协议开源。
FFmpeg 为可选或外挂的多媒体编码核心工具，其二进制遵循 LGPL/GPL 协议。
