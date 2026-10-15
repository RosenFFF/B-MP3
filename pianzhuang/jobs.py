"""格式转换、音频提取和视频总结。"""

from __future__ import annotations

import hashlib
import math
import re
import tempfile
import threading
from pathlib import Path

from pianzhuang.media import (
    available_audio_formats,
    brief_error,
    probe_media,
    remove_output,
    repaired_path,
    run_ffmpeg,
    safe_name,
    unique_path,
)
from pianzhuang.models import JobResult, MediaItem, Settings
from pianzhuang.report import build_report

Progress = callable
Log = callable
ItemHook = callable


def convert_items(items, settings, log, on_progress, cancel, on_item) -> list[JobResult]:
    return _run_batch(items, settings, log, on_progress, cancel, on_item, convert_one, "转换")


def audio_items(items, settings, log, on_progress, cancel, on_item) -> list[JobResult]:
    return _run_batch(items, settings, log, on_progress, cancel, on_item, extract_one, "提取音频")


def summary_items(items, settings, log, on_progress, cancel, on_item) -> list[JobResult]:
    return _run_batch(items, settings, log, on_progress, cancel, on_item, summary_one, "总结")


def _run_batch(items, settings: Settings, log: Log, on_progress: Progress, cancel: threading.Event, on_item: ItemHook, worker, label: str) -> list[JobResult]:
    results: list[JobResult] = []
    total = len(items)
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    for index, item in enumerate(items):
        if cancel.is_set():
            _cancel_rest(items[index:], on_item, results)
            break
        on_item(item, "处理中", f"正在{label}")

        def progress(fraction: float, index=index) -> None:
            on_progress((index + max(0.0, min(1.0, fraction))) / total)

        log(f"正在{label}：{item.title}")
        try:
            result = worker(item, settings, log, progress, cancel)
        except Exception as exc:  # noqa: BLE001 - 一条失败不影响队列里的其他文件
            result = JobResult(False, None, str(exc))
        results.append(result)
        if result.cancelled:
            on_item(item, "已取消", "已停止")
            log(f"已停止：{item.title}")
            _cancel_rest(items[index + 1 :], on_item, results)
            break
        if result.ok and result.output:
            on_item(item, "完成", f"输出 {result.output.name}")
            log(f"已输出：{result.output}")
        else:
            on_item(item, "失败", result.message or "失败")
            log(f"失败：{item.title}")
            if result.message:
                log(result.message)
    if results and not any(item.cancelled for item in results):
        on_progress(1.0)
    return results


def _cancel_rest(items, on_item, results) -> None:
    for item in items:
        on_item(item, "已取消", "已停止")
        results.append(JobResult(False, None, "已取消", True))


def convert_one(item: MediaItem, settings: Settings, log, on_progress, cancel: threading.Event) -> JobResult:
    if not item.videos:
        return JobResult(False, None, "没有画面，不能转成视频。可以改用「提取音频」。")
    container = settings.container_ext()
    preset = settings.preset if settings.preset in {"快速封装", "标准", "高画质", "较小文件"} else "标准"
    with tempfile.TemporaryDirectory(prefix="pianzhuang-") as folder:
        work = Path(folder)
        videos = [_stage(path, work, log) for path in item.videos]
        if cancel.is_set():
            return JobResult(False, None, "已取消", True)
        if len(videos) > 1:
            joined = work / "joined.mkv"
            concatenated = _concat(videos, joined, log, on_progress, cancel)
            if concatenated.cancelled:
                return JobResult(False, None, "已取消", True)
            if not concatenated.ok:
                return JobResult(False, None, brief_error(concatenated.stderr))
            videos = [joined]
        video = videos[0]
        audio = _stage(item.audios[0], work, log) if item.audios else None
        video_info = probe_media(video)
        audio_info = probe_media(audio) if audio else None
        if video_info is None or not video_info.has_video:
            return JobResult(False, None, "没有读到画面。文件可能已损坏，或不是视频。")
        acodec = ""
        if audio_info and audio_info.has_audio:
            acodec = audio_info.acodec
        elif video_info.has_audio:
            acodec = video_info.acodec
        out_v, out_a, vf, crf = _encoding_plan(preset, container, video_info.vcodec, acodec)
        if preset == "快速封装" and out_v != "copy":
            log("这个画面编码不能直接放进目标格式，已改为转码。")
        if preset == "快速封装" and acodec and out_a not in {None, "copy"}:
            log("音轨不能直接封装，已转成 AAC。")
        destination = unique_path(settings.output_dir / f"{safe_name(item.title)}.{container}")
        duration = max(video_info.duration, audio_info.duration if audio_info else 0)
        subtitle = item.subtitle if item.subtitle and item.subtitle.is_file() else None
        if subtitle:
            log(f"附带字幕：{subtitle.name}")

        def build(include_sub: bool) -> list[str]:
            args = ["-i", str(video)]
            next_index = 1
            audio_map = None
            if audio is not None:
                args += ["-i", str(audio)]
                audio_map = f"{next_index}:a:0"
                next_index += 1
            elif video_info.has_audio:
                audio_map = "0:a:0"
            sub_map = None
            if include_sub and subtitle is not None:
                args += ["-i", str(subtitle)]
                sub_map = f"{next_index}:s:0"
            args += ["-map", "0:V:0"]
            if audio_map and out_a:
                args += ["-map", audio_map]
            if sub_map:
                args += ["-map", sub_map]
            args += ["-c:v", out_v]
            if out_v == "libx264":
                args += ["-preset", "medium", "-crf", crf, "-pix_fmt", "yuv420p"]
            if vf:
                args += ["-vf", vf]
            if audio_map and out_a:
                args += ["-c:a", out_a]
                if out_a == "aac":
                    args += ["-b:a", "192k"]
            else:
                args += ["-an"]
            if sub_map:
                args += ["-c:s", "copy" if container == "mkv" else "mov_text"]
            args += ["-metadata", f"title={item.title}"]
            if container in {"mp4", "mov"}:
                args += ["-movflags", "+faststart"]
            args.append(str(destination))
            return args

        result = run_ffmpeg(build(True), duration=duration, on_progress=on_progress, cancel=cancel)
        if result.cancelled:
            remove_output(destination)
            return JobResult(False, None, "已取消", True)
        if not result.ok and subtitle is not None:
            log("字幕没有写进文件，改为不带字幕再试一次。")
            remove_output(destination)
            result = run_ffmpeg(build(False), duration=duration, on_progress=on_progress, cancel=cancel)
        if result.cancelled:
            remove_output(destination)
            return JobResult(False, None, "已取消", True)
        if not result.ok:
            remove_output(destination)
            return JobResult(False, None, brief_error(result.stderr))
        return JobResult(True, destination, "完成")


def extract_one(item: MediaItem, settings: Settings, log, on_progress, cancel: threading.Event) -> JobResult:
    chosen = settings.audio_format.upper()
    formats = set(available_audio_formats())
    if chosen not in formats:
        chosen = "M4A" if "M4A" in formats else "WAV"
        log(f"当前 FFmpeg 没有这个音频编码器，已改用 {chosen}。")
    with tempfile.TemporaryDirectory(prefix="pianzhuang-") as folder:
        work = Path(folder)
        if item.audios:
            source = _stage(item.audios[0], work, log)
        elif len(item.videos) == 1:
            source = _stage(item.videos[0], work, log)
        elif item.videos:
            staged = [_stage(path, work, log) for path in item.videos]
            source = work / "joined.mkv"
            concatenated = _concat(staged, source, log, on_progress, cancel)
            if concatenated.cancelled:
                return JobResult(False, None, "已取消", True)
            if not concatenated.ok:
                return JobResult(False, None, brief_error(concatenated.stderr))
        else:
            return JobResult(False, None, "没有可提取的音轨。")
        info = probe_media(source)
        if info is None or not info.has_audio:
            return JobResult(False, None, "没有读到音轨。")
        extension, codec_args = _audio_args(chosen, info.acodec)
        destination = unique_path(settings.output_dir / f"{safe_name(item.title)}{extension}")
        args = ["-i", str(source), "-vn", "-map", "0:a:0", *codec_args, str(destination)]
        result = run_ffmpeg(args, duration=info.duration, on_progress=on_progress, cancel=cancel)
        if result.cancelled:
            remove_output(destination)
            return JobResult(False, None, "已取消", True)
        if not result.ok:
            remove_output(destination)
            return JobResult(False, None, brief_error(result.stderr))
        return JobResult(True, destination, "完成")


def summary_one(item: MediaItem, settings: Settings, log, on_progress, cancel: threading.Event) -> JobResult:
    if not item.videos and not item.audios:
        return JobResult(False, None, "没有可总结的文件。")
    digest = hashlib.sha1(repr(item.key).encode("utf-8")).hexdigest()[:6]
    folder = settings.output_dir / "总结" / f"{safe_name(item.title)}-{digest}"
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pianzhuang-") as temp_name:
        work = Path(temp_name)
        video = _materialize_video(item, work, log, on_progress, cancel)
        if isinstance(video, JobResult):
            return video
        audio = _stage(item.audios[0], work, log) if item.audios else None
        video_info = probe_media(video) if video else None
        audio_info = probe_media(audio) if audio else None
        if audio is None and video_info and video_info.has_audio:
            audio = video
            audio_info = video_info
        if (video_info is None or not (video_info.has_video or video_info.has_audio)) and (
            audio_info is None or not audio_info.has_audio
        ):
            return JobResult(False, None, "没有读到画面或音轨。")
        base = video_info or audio_info
        assert base is not None
        facts = {
            "duration": max(video_info.duration if video_info else 0, audio_info.duration if audio_info else 0),
            "width": video_info.width if video_info else 0,
            "height": video_info.height if video_info else 0,
            "fps": video_info.fps if video_info else 0,
            "vcodec": video_info.vcodec if video_info else "",
            "acodec": (audio_info.acodec if audio_info and audio_info.acodec else base.acodec),
            "bitrate": base.bitrate,
            "size": _source_size(item),
            "format_name": base.format_name,
            "chapters": video_info.chapters if video_info else [],
        }
        on_progress(0.08)
        sheet = folder / "storyboard.jpg"
        sheet_name = None
        if video_info and video_info.has_video and video is not None:
            if _storyboard(video, sheet, facts["duration"], on_progress, cancel):
                sheet_name = sheet.name
            elif cancel.is_set():
                return JobResult(False, None, "已取消", True)
            else:
                log("分镜拼图没有生成，总结里会保留文字信息。")
        on_progress(0.4)
        scenes: list[float] = []
        if video_info and video_info.has_video and video is not None:
            scenes = _scenes(video, facts["duration"], log, on_progress, cancel)
            if cancel.is_set():
                return JobResult(False, None, "已取消", True)
        on_progress(0.82)
        loudness: dict[str, str] = {}
        if audio is not None and audio_info and audio_info.has_audio:
            loudness = _loudness(audio, log, cancel)
            if cancel.is_set():
                return JobResult(False, None, "已取消", True)
        report = folder / "总结.md"
        build_report(item, facts, loudness, scenes, sheet_name, report)
        on_progress(1.0)
        return JobResult(True, report, "完成")


def _stage(path: Path, work: Path, log) -> Path:
    repaired = repaired_path(path, work)
    if repaired != path:
        log(f"已去掉 {path.name} 开头的非标准数据。")
    return repaired


def _concat(paths: list[Path], dest: Path, log, on_progress, cancel: threading.Event):
    listing = dest.with_suffix(".txt")
    lines = [_concat_line(path) for path in paths]
    listing.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    copied = run_ffmpeg(
        ["-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(dest)],
        on_progress=on_progress,
        cancel=cancel,
    )
    if copied.ok or copied.cancelled:
        return copied
    log("分段不能直接拼接，改为转码后再拼接。")
    remove_output(dest)
    return run_ffmpeg(
        [
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(listing),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-pix_fmt",
            "yuv420p",
            str(dest),
        ],
        on_progress=on_progress,
        cancel=cancel,
    )


def _concat_line(path: Path) -> str:
    text = path.resolve().as_posix().replace("'", r"'\''")
    return f"file '{text}'"


def _encoding_plan(preset: str, container: str, vcodec: str, acodec: str):
    has_audio = bool(acodec)
    copy_video = bool(vcodec) and (container == "mkv" or vcodec in {"h264", "hevc", "mpeg4", "av1"})
    copy_audio = has_audio and (container == "mkv" or acodec in {"aac", "mp3", "ac3", "eac3", "alac"})
    if preset == "快速封装":
        out_v = "copy" if copy_video else "libx264"
        out_a = None if not has_audio else ("copy" if copy_audio else "aac")
        return out_v, out_a, None, "23"
    profiles = {
        "高画质": ("18", None),
        "较小文件": ("28", "scale=min(1280\\,iw):-2"),
        "标准": ("23", None),
    }
    crf, vf = profiles.get(preset, ("23", None))
    return "libx264", ("aac" if has_audio else None), vf, crf


def _audio_args(fmt: str, source_codec: str) -> tuple[str, list[str]]:
    if fmt == "MP3":
        if source_codec == "mp3":
            return ".mp3", ["-c:a", "copy"]
        return ".mp3", ["-c:a", "libmp3lame", "-q:a", "2"]
    if fmt == "WAV":
        return ".wav", ["-c:a", "pcm_s16le"]
    if fmt == "FLAC":
        if source_codec == "flac":
            return ".flac", ["-c:a", "copy"]
        return ".flac", ["-c:a", "flac"]
    if source_codec == "aac":
        return ".m4a", ["-c:a", "copy"]
    return ".m4a", ["-c:a", "aac", "-b:a", "192k"]


def _materialize_video(item: MediaItem, work: Path, log, on_progress, cancel):
    if not item.videos:
        return None
    staged = [_stage(path, work, log) for path in item.videos]
    if len(staged) == 1:
        return staged[0]
    dest = work / "joined.mkv"
    concatenated = _concat(staged, dest, log, on_progress, cancel)
    if concatenated.cancelled:
        return JobResult(False, None, "已取消", True)
    if concatenated.ok:
        return dest
    log("分段拼接失败，总结改用第一段画面。")
    return staged[0]


def _storyboard(video: Path, dest: Path, duration: float, on_progress, cancel) -> bool:
    span = duration if duration > 0 else 1
    count = 9 if span >= 3 else 4 if span >= 1 else 1
    columns = 3 if count >= 9 else 2 if count >= 4 else 1
    rows = max(1, math.ceil(count / columns))
    fps = count / span
    video_filter = f"fps={fps:.6f},scale=320:-2,tile={columns}x{rows}"
    result = run_ffmpeg(
        ["-i", str(video), "-an", "-vf", video_filter, "-frames:v", "1", "-q:v", "3", str(dest)],
        duration=span,
        on_progress=lambda fraction: on_progress(0.08 + fraction * 0.28),
        cancel=cancel,
    )
    return result.ok and dest.is_file() and dest.stat().st_size > 0


def _scenes(video: Path, duration: float, log, on_progress, cancel) -> list[float]:
    found: list[float] = []

    def take(line: str) -> None:
        match = re.search(r"pts_time:([0-9.]+)", line)
        if match and len(found) < 40:
            found.append(float(match.group(1)))

    result = run_ffmpeg(
        ["-i", str(video), "-an", "-filter:v", "select=gt(scene\\,0.35),showinfo", "-f", "null", "-"],
        duration=duration,
        on_progress=lambda fraction: on_progress(0.4 + fraction * 0.4),
        on_line=take,
        cancel=cancel,
    )
    if not result.ok and not result.cancelled:
        log("场景检测没有完成，总结里会保留其他信息。")
        return []
    return found


def _loudness(audio: Path, log, cancel) -> dict[str, str]:
    found: dict[str, str] = {}

    def take(line: str) -> None:
        if "mean_volume:" in line:
            found["mean"] = line.split("mean_volume:", 1)[1].strip()
        if "max_volume:" in line:
            found["max"] = line.split("max_volume:", 1)[1].strip()

    result = run_ffmpeg(
        ["-i", str(audio), "-vn", "-af", "volumedetect", "-f", "null", "-"],
        on_line=take,
        cancel=cancel,
    )
    if not result.ok and not result.cancelled:
        log("响度检测没有完成。")
        return {}
    return found


def _source_size(item: MediaItem) -> int:
    total = 0
    for path in [*item.videos, *item.audios]:
        try:
            total += path.stat().st_size
        except OSError:
            pass
    return total
