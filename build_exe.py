"""打包「光影工坊」为 Windows 可执行程序 (.exe)。
将图标、主题依赖以及本地 vendor/bin (FFmpeg/FFprobe) 自动整合到发布目录中。
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
PYINSTALLER = ROOT / ".venv" / "Scripts" / "pyinstaller.exe"
RESOURCES = ROOT / "resources"
VENDOR_BIN = ROOT / "vendor" / "bin"
DIST = ROOT / "dist"
BUILD = ROOT / "build"


def build():
    if not PYINSTALLER.is_file():
        print(f"Error: {PYINSTALLER} not found.")
        sys.exit(1)

    icon_path = RESOURCES / "icon.ico"
    if not icon_path.is_file():
        print("Generating icons first...")
        subprocess.run([str(PYTHON), str(ROOT / "process_icon.py")], check=True)

    print("=== 开始使用 PyInstaller 构建「光影工坊」 ===")
    
    cmd = [
        str(PYINSTALLER),
        "--clean",
        "-y",
        str(ROOT / "app.spec"),
    ]

    print("执行命令:", " ".join(cmd))
    res = subprocess.run(cmd, cwd=str(ROOT))
    if res.returncode != 0:
        print("PyInstaller 构建失败！")
        sys.exit(res.returncode)

    temp_dist_dir = DIST / "LuminaStudio"
    if not temp_dist_dir.is_dir():
        print(f"Error: {temp_dist_dir} does not exist.")
        sys.exit(1)

    # 复制 resources 目录
    dest_res = temp_dist_dir / "resources"
    dest_res.mkdir(parents=True, exist_ok=True)
    for item in RESOURCES.iterdir():
        if item.is_file():
            shutil.copy2(item, dest_res / item.name)

    # 复制 vendor/bin 目录中的 ffmpeg.exe 与 ffprobe.exe
    dest_vendor_bin = temp_dist_dir / "vendor" / "bin"
    dest_vendor_bin.mkdir(parents=True, exist_ok=True)
    for tool_name in ("ffmpeg.exe", "ffprobe.exe"):
        src_tool = VENDOR_BIN / tool_name
        if src_tool.is_file():
            print(f"正在复制 {tool_name} 到打包目录...")
            shutil.copy2(src_tool, dest_vendor_bin / tool_name)
        else:
            print(f"警告：未找到 {src_tool}")

    # 生成「光影工坊.exe」
    lumina_exe = temp_dist_dir / "LuminaStudio.exe"
    chinese_exe = temp_dist_dir / "光影工坊.exe"
    if lumina_exe.is_file():
        shutil.copy2(lumina_exe, chinese_exe)

    # 重命名目录为「光影工坊」
    final_dist_dir = DIST / "光影工坊"
    if final_dist_dir.is_dir():
        shutil.rmtree(final_dist_dir)
    shutil.move(str(temp_dist_dir), str(final_dist_dir))

    final_exe = final_dist_dir / "光影工坊.exe"
    print("\n==========================================")
    print("【构建成功】独立免安装便携版已生成：")
    print(f"应用目录: {final_dist_dir}")
    print(f"主程序:   {final_exe}")
    if final_exe.is_file():
        print(f"大小:     {final_exe.stat().st_size / 1024 / 1024:.2f} MB")
    print("已打包集成 FFmpeg、FFprobe 与定制图标，直接双击运行！")
    print("==========================================\n")


if __name__ == "__main__":
    build()
