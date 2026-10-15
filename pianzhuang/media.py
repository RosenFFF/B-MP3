"""探测媒体、修掉缓存文件开头的杂数据，并调用 FFmpeg。"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from pianzhuang.binaries import CREATE_NO_WINDOW, ffmpeg_path, ffprobe_path

_ENCODER_TEXT: str | None = None


@dataclass
class Probe:
    duration: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    vcodec: str = ""
    acodec: str = ""
    bitrate: int = 0
    size: int = 0
    has_video: bool = False
    has_audio: bool = False
    format_name: str = ""
    chapters: list[tuple[float, str]] = field(default_factory=list)


@dataclass
class FFmpegResult:
    code: int
    stderr: str = ""
    cancelled: bool = False

    @property
    def ok(self) -> bool:
        return self.code == 0 and not self.cancelled


def encoder_text(refresh: bool = False) -> str:
    global _ENCODER_TEXT
    if _ENCODER_TEXT is not None and not refresh:
        return _ENCODER_TEXT
    exe = ffmpeg_path()
    if exe is None:
        return ""
    try:
        completed = subprocess.run(
            [str(exe), "-hide_banner", "-encoders"],
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
    _ENCODER_TEXT = completed.stdout or ""
    return _ENCODER_TEXT


def has_encoder(name: str) -> bool:
    return re.search(rf"(?m)^ A\S{{5}} {re.escape(name)}(?:\s|$)", encoder_text()) is not None


def available_audio_formats() -> list[str]:
    if ffmpeg_path() is None:
        return ["MP3", "M4A", "WAV", "FLAC"]
    found: list[str] = []
    if has_encoder("libmp3lame"):
        found.append("MP3")
    if has_encoder("aac"):
        found.append("M4A")
    found.append("WAV")
    if has_encoder("flac"):
        found.append("FLAC")
    return found


def safe_name(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]', " ", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().rstrip(".")
    if not cleaned:
        return "未命名"
    return cleaned[:80]


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(1, 1000):
        candidate = path.with_name(f"{path.stem} ({index}){path.suffix}")
        if not candidate.exists():
            return candidate
    return path.with_name(f"{path.stem}-{uuid.uuid4().hex[:6]}{path.suffix}")


def format_duration(seconds: float) -> str:
    if seconds <= 0:
        return "未知"
    whole = int(round(seconds))
    hours, rem = divmod(whole, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def format_timestamp(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    millis = int(round(seconds * 1000))
    hours, rem = divmod(millis, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, milli = divmod(rem, 1000)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{milli:03d}"
    return f"{minutes:02d}:{secs:02d}.{milli:03d}"


def format_size(size: int) -> str:
    value = float(max(size, 0))
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def format_bitrate(bps: int) -> str:
    if bps <= 0:
        return "未知"
    if bps >= 1_000_000:
        return f"{bps / 1_000_000:.2f} Mbps"
    if bps >= 1000:
        return f"{bps / 1000:.0f} kbps"
    return f"{bps} bps"


def parse_ffmpeg_time(value: str) -> float:
    text = value.strip()
    parts = text.split(":")
    if len(parts) != 3:
        return float(text)
    return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])


def brief_error(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in reversed(lines):
        lower = line.lower()
        if "error" in lower or "invalid" in lower or "failed" in lower or "not found" in lower:
            return line[:300]
    if lines:
        return lines[-1][:300]
    return "FFmpeg 没有完成。"


def _float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _int(value) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _frame_rate(value: str) -> float:
    if not value or value == "0/0":
        return 0.0
    if "/" in value:
        left, right = value.split("/", 1)
        denominator = _float(right)
        if denominator == 0:
            return 0.0
        return _float(left) / denominator
    return _float(value)


_MEDIA_BOXES = {
    b"ftyp",
    b"styp",
    b"moov",
    b"moof",
    b"mdat",
    b"free",
    b"skip",
    b"sidx",
    b"wide",
    b"uuid",
    b"meta",
    b"pdin",
    b"ssix",
    b"emsg",
}


def _box_type(head: bytes, offset: int) -> bytes | None:
    if len(head) < offset + 8:
        return None
    size = int.from_bytes(head[offset : offset + 4], "big")
    kind = head[offset + 4 : offset + 8]
    if size < 8 or not kind.isalnum():
        return None
    return kind


def container_start(head: bytes) -> int | None:
    """返回真正容器数据的起点。0 表示文件本身就能读。None 表示不用改。"""
    if not head:
        return None
    if head.startswith((b"FLV", b"\x1aE\xdf\xa3", b"RIFF", b"OggS", b"ID3")):
        return 0
    if _box_type(head, 0) in _MEDIA_BOXES:
        return 0
    limit = min(len(head), 2048)
    ftyp_at = head.find(b"ftyp")
    if 4 <= ftyp_at < limit and _box_type(head, ftyp_at - 4) == b"ftyp":
        return ftyp_at - 4
    flv_at = head.find(b"FLV")
    if 0 < flv_at < 64:
        return flv_at
    return None


def repaired_path(src: Path, work: Path) -> Path:
    """有些 B 站缓存会在 ftyp 或 FLV 前面多一段数据。只在检测到时才另存一份。"""
    try:
        with src.open("rb") as handle:
            head = handle.read(8192)
    except OSError:
        return src
    start = container_start(head)
    if not start:
        return src
    work.mkdir(parents=True, exist_ok=True)
    dest = work / f"repair-{safe_name(src.stem)}{src.suffix.lower()}"
    if dest.exists():
        dest = work / f"repair-{safe_name(src.stem)}-{uuid.uuid4().hex[:4]}{src.suffix.lower()}"
    with src.open("rb") as source, dest.open("wb") as handle:
        source.seek(start)
        shutil.copyfileobj(source, handle, length=1024 * 1024)
    return dest


def probe_raw(path: Path) -> Probe | None:
    exe = ffprobe_path()
    if exe is None or not path.is_file():
        return None
    command = [
        str(exe),
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        "-show_chapters",
        str(path),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=CREATE_NO_WINDOW,
            stdin=subprocess.DEVNULL,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0 or not completed.stdout.strip():
        return None
    try:
        data = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None
    return _probe_from_json(data, path)


def probe_media(path: Path) -> Probe | None:
    info = probe_raw(path)
    if info and (info.has_video or info.has_audio):
        return info
    with tempfile.TemporaryDirectory(prefix="pianzhuang-probe-") as folder:
        repaired = repaired_path(path, Path(folder))
        if repaired == path:
            return info
        return probe_raw(repaired)


def _probe_from_json(data: dict, path: Path) -> Probe:
    video = None
    audio = None
    for stream in data.get("streams") or []:
        if not isinstance(stream, dict):
            continue
        kind = stream.get("codec_type")
        disposition = stream.get("disposition") or {}
        if kind == "video" and video is None and not disposition.get("attached_pic"):
            video = stream
        elif kind == "audio" and audio is None:
            audio = stream
    fmt = data.get("format") or {}
    duration = _float(fmt.get("duration"))
    if duration <= 0 and video:
        duration = _float(video.get("duration"))
    if duration <= 0 and audio:
        duration = _float(audio.get("duration"))
    size = _int(fmt.get("size"))
    if size <= 0:
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
    chapters: list[tuple[float, str]] = []
    for chapter in data.get("chapters") or []:
        if not isinstance(chapter, dict):
            continue
        title = str((chapter.get("tags") or {}).get("title") or "").strip()
        chapters.append((_float(chapter.get("start_time")), title))
    fps = 0.0
    if video:
        fps = _frame_rate(str(video.get("avg_frame_rate") or video.get("r_frame_rate") or ""))
    return Probe(
        duration=duration,
        width=_int(video.get("width")) if video else 0,
        height=_int(video.get("height")) if video else 0,
        fps=fps,
        vcodec=str(video.get("codec_name") or "") if video else "",
        acodec=str(audio.get("codec_name") or "") if audio else "",
        bitrate=_int(fmt.get("bit_rate")),
        size=size,
        has_video=video is not None,
        has_audio=audio is not None,
        format_name=str(fmt.get("format_name") or ""),
        chapters=chapters,
    )


def run_ffmpeg(
    args: list[str],
    *,
    duration: float | None = None,
    on_progress=None,
    on_line=None,
    cancel: threading.Event | None = None,
) -> FFmpegResult:
    exe = ffmpeg_path()
    if exe is None:
        return FFmpegResult(code=1, stderr="未找到 FFmpeg。")
    command = [str(exe), "-hide_banner", "-nostdin", "-y", "-progress", "pipe:1", "-nostats", *args]
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        creationflags=CREATE_NO_WINDOW,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    stderr_lines: list[str] = []

    def read_stderr() -> None:
        assert process.stderr is not None
        for line in process.stderr:
            text = line.rstrip()
            stderr_lines.append(text)
            if len(stderr_lines) > 4000:
                del stderr_lines[:1000]
            if on_line:
                on_line(text)

    reader = threading.Thread(target=read_stderr, daemon=True)
    reader.start()

    def watch_cancel() -> None:
        if cancel is None:
            return
        while process.poll() is None:
            if cancel.is_set():
                process.terminate()
                return
            cancel.wait(0.2)

    watcher = threading.Thread(target=watch_cancel, daemon=True)
    watcher.start()

    assert process.stdout is not None
    try:
        for line in process.stdout:
            if cancel is not None and cancel.is_set():
                process.terminate()
                break
            text = line.strip()
            if text.startswith("out_time=") and duration and duration > 0 and on_progress:
                try:
                    seconds = parse_ffmpeg_time(text.split("=", 1)[1])
                    on_progress(max(0.0, min(0.99, seconds / duration)))
                except ValueError:
                    pass
            elif text == "progress=end" and on_progress:
                on_progress(1.0)
    finally:
        try:
            process.wait(timeout=120)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
    reader.join(timeout=2)
    if process.stdout is not None:
        process.stdout.close()
    if process.stderr is not None:
        process.stderr.close()
    cancelled = bool(cancel and cancel.is_set())
    if cancelled and process.poll() is None:
        process.kill()
    return FFmpegResult(
        code=-2 if cancelled else (process.returncode if process.returncode is not None else 1),
        stderr="\n".join(stderr_lines[-80:]),
        cancelled=cancelled,
    )


def remove_output(path: Path | None) -> None:
    if path is None:
        return
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        pass
