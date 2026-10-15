"""记住输出目录和画质选择。"""

from __future__ import annotations

import json
import os
from pathlib import Path

from pianzhuang.models import AUDIO_FORMATS, CONTAINERS, PRESETS


def app_dir() -> Path:
    root = os.environ.get("APPDATA")
    base = Path(root) if root else Path.home()
    lumina = base / "LuminaStudio"
    old = base / "PianZhuan"
    if not lumina.exists() and old.is_dir():
        return old
    return lumina


def default_output() -> Path:
    videos = Path.home() / "Videos"
    base = videos if videos.is_dir() else Path.home()
    return base / "光影工坊输出"


def load_settings() -> dict:
    path = app_dir() / "config.json"
    data: dict = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except (OSError, json.JSONDecodeError):
            data = {}
    preset = data.get("preset")
    container = data.get("container")
    audio = data.get("audio_format")
    return {
        "output_dir": str(data.get("output_dir") or default_output()),
        "preset": preset if preset in PRESETS else "标准",
        "container": container if container in CONTAINERS else "MP4",
        "audio_format": audio if audio in AUDIO_FORMATS else "MP3",
    }


def save_settings(data: dict) -> None:
    folder = app_dir()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "config.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def append_log(message: str) -> None:
    try:
        folder = app_dir()
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "last.log"
        if path.is_file() and path.stat().st_size > 300_000:
            path.unlink()
        with path.open("a", encoding="utf-8") as handle:
            handle.write(message.rstrip() + "\n")
    except OSError:
        return
