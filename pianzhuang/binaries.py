"""找到 FFmpeg。没有的话，可以把 Windows essentials 构建下载到 vendor/bin。"""

from __future__ import annotations

import shutil
import subprocess
import urllib.request
import zipfile
import sys
from pathlib import Path

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).parent
else:
    ROOT = Path(__file__).resolve().parents[1]

VENDOR_BIN = ROOT / "vendor" / "bin"

URLS = (
    "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
)


def ffmpeg_path() -> Path | None:
    return _tool("ffmpeg.exe")


def ffprobe_path() -> Path | None:
    return _tool("ffprobe.exe")


def _tool(name: str) -> Path | None:
    candidates = []
    if hasattr(sys, "_MEIPASS"):
        candidates.append(Path(sys._MEIPASS) / "vendor" / "bin" / name)
        candidates.append(Path(sys._MEIPASS) / name)
    exe_dir = Path(sys.executable).parent
    candidates.append(exe_dir / "vendor" / "bin" / name)
    candidates.append(exe_dir / name)
    candidates.append(VENDOR_BIN / name)

    for cand in candidates:
        if cand.is_file():
            return cand

    found = shutil.which(name) or shutil.which(name.removesuffix(".exe"))
    return Path(found) if found else None


def ffmpeg_version_line() -> str:
    exe = ffmpeg_path()
    if exe is None:
        return ""
    try:
        completed = subprocess.run(
            [str(exe), "-version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=CREATE_NO_WINDOW,
            stdin=subprocess.DEVNULL,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    lines = (completed.stdout or "").splitlines()
    if not lines:
        return ""
    return lines[0].split(" Copyright", 1)[0].strip()


def ensure_ffmpeg(download: bool = False, log=None) -> Path:
    ready = ffmpeg_path()
    if ready is not None and ffprobe_path() is not None:
        return ready
    if not download:
        raise RuntimeError("未找到 FFmpeg。")

    VENDOR_BIN.mkdir(parents=True, exist_ok=True)
    zip_path = VENDOR_BIN.parent / "ffmpeg-essentials.zip"
    if zip_path.is_file() and zip_path.stat().st_size > 1_000_000:
        if log:
            log("使用已经下载的 FFmpeg 压缩包。")
        try:
            _extract(zip_path, VENDOR_BIN)
        except zipfile.BadZipFile:
            zip_path.unlink(missing_ok=True)

    ready = ffmpeg_path()
    if ready is not None and ffprobe_path() is not None:
        return ready

    last_error = "下载失败"
    for url in URLS:
        if log:
            log(f"正在下载 FFmpeg：{url}")
        try:
            _download(url, zip_path, log)
            _extract(zip_path, VENDOR_BIN)
        except Exception as exc:  # noqa: BLE001 - 换下一条下载地址
            last_error = str(exc)
            if log:
                log(f"这一路没有下完：{exc}")
            continue
        ready = ffmpeg_path()
        if ready is not None and ffprobe_path() is not None:
            return ready
    raise RuntimeError(last_error)


def _download(url: str, dest: Path, log) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 LuminaStudio"})
    with urllib.request.urlopen(request, timeout=60) as response, dest.open("wb") as handle:
        total = int(response.headers.get("Content-Length") or 0)
        read = 0
        last_note = 0
        while True:
            chunk = response.read(256 * 1024)
            if not chunk:
                break
            handle.write(chunk)
            read += len(chunk)
            if log and total and read - last_note >= 8 * 1024 * 1024:
                last_note = read
                log(f"已下载 {read * 100 // total}%")


def _extract(zip_path: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    found = False
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            base = info.filename.replace("\\", "/").rsplit("/", 1)[-1].lower()
            if base not in {"ffmpeg.exe", "ffprobe.exe"}:
                continue
            target = dest / base
            with archive.open(info) as source, target.open("wb") as handle:
                shutil.copyfileobj(source, handle, length=1024 * 1024)
            found = True
    if not found:
        raise RuntimeError("压缩包里没有 ffmpeg.exe。")
