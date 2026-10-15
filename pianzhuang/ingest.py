"""从文件、文件夹和 B 站客户端缓存目录收集要处理的条目。"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from pianzhuang.binaries import ffmpeg_path
from pianzhuang.media import Probe, format_duration, format_size, probe_media
from pianzhuang.models import Kind, MediaItem

MEDIA_EXT = {
    ".mp4",
    ".mkv",
    ".avi",
    ".mov",
    ".wmv",
    ".webm",
    ".ts",
    ".m2ts",
    ".mts",
    ".m4v",
    ".mpg",
    ".mpeg",
    ".3gp",
    ".vob",
    ".f4v",
}
AUDIO_EXT = {".mp3", ".m4a", ".wav", ".aac", ".flac", ".ogg", ".opus", ".wma"}
SUB_EXT = {".srt", ".ass", ".ssa", ".vtt"}
INTERESTING_EXT = MEDIA_EXT | AUDIO_EXT | {".m4s", ".blv", ".flv"}

_URL_HINT = re.compile(r"(bilibili\.com|b23\.tv|\bBV[0-9A-Za-z]{10}\b)", re.IGNORECASE)


def default_bili_roots() -> list[Path]:
    home = Path.home()
    local = os.environ.get("LOCALAPPDATA", "")
    candidates = [
        home / "Videos" / "bilibili",
        home / "Videos" / "bilibili" / "download",
        home / "Video" / "bilibili",
        Path(local) / "bilibili" if local else None,
        Path(local) / "bilibili" / "download" if local else None,
    ]
    videos = home / "Videos"
    if videos.is_dir():
        try:
            for child in videos.iterdir():
                if child.is_dir() and "bili" in child.name.lower():
                    candidates.append(child)
        except OSError:
            pass
    found: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate is None or not candidate.is_dir():
            continue
        try:
            key = str(candidate.resolve()).lower()
        except OSError:
            key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        found.append(candidate)
    return found


def parse_dropped_text(text: str) -> tuple[list[Path], str | None]:
    raw = text.strip()
    if not raw:
        return [], "剪贴板是空的。"
    if _is_plain_url(raw):
        return [], "这是网页链接。光影工坊只处理本机文件和 B 站客户端已经下载的缓存，不会从网站下载视频。"

    quoted = re.findall(r'"([^"]+)"', raw)
    if quoted and all(_looks_like_path(item) for item in quoted):
        candidates = quoted
    else:
        lines = [line.strip().strip('"') for line in raw.splitlines() if line.strip()]
        if lines and all(_looks_like_path(line) for line in lines):
            candidates = lines
        elif raw.lower().startswith("file:"):
            candidates = [_file_uri_path(raw)]
        else:
            candidates = []

    paths: list[Path] = []
    missing = 0
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            paths.append(path)
        else:
            missing += 1
    if paths:
        return paths, None
    if _URL_HINT.search(raw):
        return [], "这是网页链接。光影工坊只处理本机文件和 B 站客户端已经下载的缓存，不会从网站下载视频。"
    if missing:
        return [], "剪贴板里的路径在这台电脑上不存在。"
    return [], "剪贴板里没有可导入的文件路径。"


def ingest_paths(paths: list[Path | str]) -> list[MediaItem]:
    items: list[MediaItem] = []
    seen: set[tuple[str, ...]] = set()
    for raw in paths:
        path = Path(raw).expanduser()
        try:
            path = path.resolve()
        except OSError:
            continue
        if not path.exists():
            continue
        found = scan_tree(path) if path.is_dir() else ingest_file(path)
        for item in found:
            if not item.key or item.key in seen:
                continue
            seen.add(item.key)
            items.append(item)
    return items


def describe_item(item: MediaItem, info: Probe | None) -> str:
    bits: list[str] = []
    if info and info.width and info.height:
        bits.append(f"{info.width}×{info.height}")
    if info and info.duration:
        bits.append(format_duration(info.duration))
    size = 0
    for path in [*item.videos, *item.audios]:
        try:
            size += path.stat().st_size
        except OSError:
            pass
    if size:
        bits.append(format_size(size))
    if item.videos and item.audios:
        bits.append("画面+音轨")
    if len(item.videos) > 1:
        bits.append(f"{len(item.videos)} 段")
    return " · ".join(bits) if bits else (item.detail or "未能读取媒体信息")


def scan_tree(root: Path) -> list[MediaItem]:
    folders: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if not name.startswith(".")]
        if any(Path(name).suffix.lower() in INTERESTING_EXT for name in filenames):
            folders.append(Path(dirpath))
    items: list[MediaItem] = []
    for folder in folders:
        try:
            files = [path for path in folder.iterdir() if path.is_file()]
        except OSError:
            continue
        items.extend(classify_folder(folder, files))
    return items


def ingest_file(path: Path) -> list[MediaItem]:
    name = path.name.lower()
    if name in {"entry.json", "danmaku.xml"}:
        return classify_folder(path.parent, _files(path.parent))
    ext = path.suffix.lower()
    if ext in {".m4s", ".blv"} or (ext == ".flv" and re.fullmatch(r"\d+", path.stem)):
        return classify_folder(path.parent, _files(path.parent))
    if ext in AUDIO_EXT:
        return [MediaItem.new(title=path.stem, kind=Kind.AUDIO, audios=[path])]
    if ext in MEDIA_EXT or ext == ".flv":
        return [
            MediaItem.new(
                title=path.stem,
                kind=Kind.VIDEO,
                videos=[path],
                subtitle=find_subtitle_for_file(path),
            )
        ]
    return []


def classify_folder(folder: Path, files: list[Path]) -> list[MediaItem]:
    files = [path for path in files if path.is_file() and not path.name.startswith(".")]
    entry_path = find_entry(folder)
    entry = read_entry(entry_path)
    title = title_from_entry(entry, folder.name)
    items: list[MediaItem] = []
    used: set[Path] = set()

    m4s = [path for path in files if path.suffix.lower() == ".m4s"]
    if m4s:
        paired, used_m4s = pair_m4s(m4s, title, folder)
        items.extend(paired)
        used.update(used_m4s)

    segments = segment_files(files)
    if segments and (
        entry_path is not None
        or any(path.suffix.lower() == ".blv" for path in segments)
        or len(segments) >= 2
    ):
        items.append(
            MediaItem.new(
                title=title,
                kind=Kind.BILI,
                videos=segments,
                subtitle=find_subtitle(folder, [title, folder.name]),
            )
        )
        used.update(segments)

    for path in files:
        if path in used:
            continue
        ext = path.suffix.lower()
        if ext in MEDIA_EXT or ext == ".flv":
            items.append(
                MediaItem.new(
                    title=path.stem,
                    kind=Kind.VIDEO,
                    videos=[path],
                    subtitle=find_subtitle_for_file(path),
                )
            )
        elif ext in AUDIO_EXT:
            items.append(MediaItem.new(title=path.stem, kind=Kind.AUDIO, audios=[path]))
    return items


def pair_m4s(m4s: list[Path], title: str, folder: Path) -> tuple[list[MediaItem], set[Path]]:
    subtitle = find_subtitle(folder, ["video", title, folder.name])
    if len(m4s) == 1:
        one = m4s[0]
        if _is_audio_name(one) and not _is_video_name(one):
            return [MediaItem.new(title=title, kind=Kind.BILI, audios=[one])], {one}
        return [MediaItem.new(title=title, kind=Kind.BILI, videos=[one], subtitle=subtitle)], {one}

    named_video = [path for path in m4s if _is_video_name(path)]
    named_audio = [path for path in m4s if _is_audio_name(path)]
    if named_video and named_audio:
        video = _prefer(named_video, "video")
        audio = _prefer(named_audio, "audio")
        used = set(named_video) | set(named_audio)
        items = [
            MediaItem.new(
                title=title,
                kind=Kind.BILI,
                videos=[video],
                audios=[audio],
                subtitle=subtitle,
            )
        ]
        return items, used

    if ffmpeg_path():
        videos: list[Path] = []
        audios: list[Path] = []
        both: list[Path] = []
        unknown: list[Path] = []
        for path in m4s:
            info = probe_media(path)
            if info is None:
                unknown.append(path)
            elif info.has_video and info.has_audio:
                both.append(path)
            elif info.has_video:
                videos.append(path)
            elif info.has_audio:
                audios.append(path)
            else:
                unknown.append(path)
        if videos and audios:
            video = max(videos, key=_file_size)
            audio = _prefer(audios, "audio")
            return [
                MediaItem.new(
                    title=title,
                    kind=Kind.BILI,
                    videos=[video],
                    audios=[audio],
                    subtitle=subtitle,
                )
            ], set(m4s)
        if both:
            return [
                MediaItem.new(title=path.stem, kind=Kind.VIDEO, videos=[path]) for path in both
            ], set(m4s)

    items = []
    for path in m4s:
        if _is_audio_name(path):
            items.append(MediaItem.new(title=path.stem, kind=Kind.AUDIO, audios=[path]))
        else:
            items.append(MediaItem.new(title=path.stem, kind=Kind.VIDEO, videos=[path]))
    return items, set(m4s)


def segment_files(files: list[Path]) -> list[Path]:
    chosen = [
        path
        for path in files
        if path.suffix.lower() == ".blv"
        or (path.suffix.lower() == ".flv" and re.fullmatch(r"\d+", path.stem) is not None)
    ]
    return sorted(chosen, key=lambda path: _natural_key(path.name))


def find_entry(folder: Path) -> Path | None:
    current = folder
    for _ in range(3):
        candidate = current / "entry.json"
        if candidate.is_file():
            return candidate
        if current.parent == current:
            break
        current = current.parent
    return None


def read_entry(path: Path | None) -> dict:
    if path is None or not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def title_from_entry(data: dict, fallback: str) -> str:
    title = str(data.get("title") or "").strip()
    part = ""
    page = data.get("page_data")
    if isinstance(page, dict):
        part = str(page.get("part") or "").strip()
    if not part:
        episode = data.get("ep")
        if isinstance(episode, dict):
            part = str(episode.get("index_title") or episode.get("index") or "").strip()
    if title and part and part not in title:
        return f"{title} {part}"
    return title or fallback


def find_subtitle(folder: Path, hints: list[str]) -> Path | None:
    try:
        files = [path for path in folder.iterdir() if path.suffix.lower() in SUB_EXT]
    except OSError:
        return None
    if not files:
        return None
    for hint in hints:
        lowered = hint.lower()
        for path in files:
            if path.stem.lower().startswith(lowered):
                return path
    return files[0]


def find_subtitle_for_file(video: Path) -> Path | None:
    for ext in (".srt", ".ass", ".ssa", ".vtt"):
        candidate = video.with_suffix(ext)
        if candidate.is_file():
            return candidate
    return find_subtitle(video.parent, [video.stem])


def _files(folder: Path) -> list[Path]:
    try:
        return [path for path in folder.iterdir() if path.is_file()]
    except OSError:
        return []


def _is_video_name(path: Path) -> bool:
    stem = path.stem.lower()
    return "video" in stem and "audio" not in stem


def _is_audio_name(path: Path) -> bool:
    return "audio" in path.stem.lower()


def _prefer(paths: list[Path], exact_stem: str) -> Path:
    exact = [path for path in paths if path.stem.lower() == exact_stem]
    pool = exact or paths
    return max(pool, key=_file_size)


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _natural_key(name: str) -> list:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", name)]


def _looks_like_path(value: str) -> bool:
    text = value.strip().strip('"')
    if re.match(r"^[A-Za-z]:[\\/]", text):
        return True
    return text.startswith("\\\\")


def _is_plain_url(value: str) -> bool:
    text = value.strip()
    if "\n" in text:
        return False
    return bool(re.match(r"https?://", text, re.IGNORECASE) and _URL_HINT.search(text))


def _file_uri_path(value: str) -> str:
    from urllib.parse import unquote, urlparse

    parsed = unquote(urlparse(value).path)
    if re.match(r"^/[A-Za-z]:", parsed):
        return parsed[1:]
    return parsed
