"""把探测结果写成一份可读的视频总结。"""

from __future__ import annotations

from pathlib import Path

from pianzhuang.media import format_bitrate, format_duration, format_size, format_timestamp
from pianzhuang.models import MediaItem


def build_report(
    item: MediaItem,
    facts: dict,
    loudness: dict[str, str],
    scenes: list[float],
    sheet_name: str | None,
    destination: Path,
) -> None:
    lines = [
        f"# {item.title}",
        "",
        "这份总结来自文件信息和画面采样：分辨率、时长、响度、分镜和场景时间。",
        "它不是对口播或剧情的文字摘要。",
        "",
        "| 项目 | 内容 |",
        "| --- | --- |",
        f"| 时长 | {_text(format_duration(float(facts.get('duration') or 0)))} |",
        f"| 分辨率 | {_resolution(facts)} |",
        f"| 帧率 | {_fps(facts)} |",
        f"| 视频编码 | {_text(facts.get('vcodec'))} |",
        f"| 音频编码 | {_text(facts.get('acodec'))} |",
        f"| 容器 | {_text(facts.get('format_name'))} |",
        f"| 码率 | {format_bitrate(int(facts.get('bitrate') or 0))} |",
        f"| 大小 | {format_size(int(facts.get('size') or 0))} |",
        "",
        "## 来源",
        "",
    ]
    if item.videos:
        for path in item.videos:
            lines.append(f"- 画面：`{path}`")
    if item.audios:
        for path in item.audios:
            lines.append(f"- 音频：`{path}`")
    if item.subtitle:
        lines.append(f"- 字幕：`{item.subtitle}`")
    if not item.videos and not item.audios:
        lines.append("- 没有可用的来源文件。")

    mean = loudness.get("mean")
    peak = loudness.get("max")
    if mean or peak:
        lines.extend(["", "## 响度", ""])
        if mean:
            lines.append(f"- 平均音量：{mean}")
        if peak:
            lines.append(f"- 峰值音量：{peak}")

    chapters = facts.get("chapters") or []
    if chapters:
        lines.extend(["", "## 章节", ""])
        for start, title in chapters:
            label = title or "未命名章节"
            lines.append(f"- {format_timestamp(float(start))} {label}")

    if scenes:
        lines.extend(["", "## 场景时间", ""])
        shown = scenes[:30]
        for stamp in shown:
            lines.append(f"- {format_timestamp(stamp)}")
        if len(scenes) > 30:
            lines.append(f"- 还有 {len(scenes) - 30} 个场景没有列在这里。")

    if sheet_name:
        lines.extend(["", "## 分镜", "", f"![分镜]({sheet_name})", ""])

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _text(value) -> str:
    text = str(value or "").strip()
    return text or "无"


def _resolution(facts: dict) -> str:
    width = int(facts.get("width") or 0)
    height = int(facts.get("height") or 0)
    if width and height:
        return f"{width}×{height}"
    return "无画面"


def _fps(facts: dict) -> str:
    fps = float(facts.get("fps") or 0)
    if fps <= 0:
        return "未知"
    return f"{fps:.3f}".rstrip("0").rstrip(".")
