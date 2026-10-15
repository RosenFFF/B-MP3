"""队列里的一条媒体，以及一次处理的设置。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Kind(str, Enum):
    VIDEO = "video"
    AUDIO = "audio"
    BILI = "bili"


PRESETS = ("快速封装", "标准", "高画质", "较小文件")
CONTAINERS = ("MP4", "MKV", "MOV")
AUDIO_FORMATS = ("MP3", "M4A", "WAV", "FLAC")


@dataclass
class MediaItem:
    id: str
    title: str
    kind: Kind
    videos: list[Path] = field(default_factory=list)
    audios: list[Path] = field(default_factory=list)
    subtitle: Path | None = None
    detail: str = ""
    status: str = "等待"

    @staticmethod
    def new(
        title: str,
        kind: Kind,
        videos: list[Path] | None = None,
        audios: list[Path] | None = None,
        subtitle: Path | None = None,
    ) -> MediaItem:
        item = MediaItem(
            id=uuid.uuid4().hex[:8],
            title=title.strip() or "未命名",
            kind=kind,
            videos=list(videos or []),
            audios=list(audios or []),
            subtitle=subtitle,
        )
        path = item.primary_path()
        item.detail = path.name if path else ""
        return item

    def primary_path(self) -> Path | None:
        if self.videos:
            return self.videos[0]
        if self.audios:
            return self.audios[0]
        return None

    @property
    def key(self) -> tuple[str, ...]:
        paths = [*self.videos, *self.audios]
        resolved: list[str] = []
        for path in paths:
            try:
                resolved.append(str(path.resolve()).lower())
            except OSError:
                resolved.append(str(path).lower())
        return tuple(resolved)


@dataclass
class Settings:
    output_dir: Path
    preset: str = "标准"
    container: str = "MP4"
    audio_format: str = "MP3"

    def container_ext(self) -> str:
        value = self.container.lower().lstrip(".")
        if value not in {"mp4", "mkv", "mov"}:
            return "mp4"
        return value


@dataclass
class JobResult:
    ok: bool
    output: Path | None = None
    message: str = ""
    cancelled: bool = False
