"""片转的核心行为。"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pianzhuang.binaries import CREATE_NO_WINDOW, ffmpeg_path
from pianzhuang.cli import main
from pianzhuang.ingest import classify_folder, ingest_paths, parse_dropped_text, title_from_entry
from pianzhuang.jobs import audio_items, convert_items, summary_items
from pianzhuang.media import container_start, probe_media, repaired_path, safe_name
from pianzhuang.models import Kind, Settings
from pianzhuang.report import build_report
from pianzhuang.sendto import install_sendto


def _ffmpeg_or_skip(test: unittest.TestCase) -> Path:
    exe = ffmpeg_path()
    if exe is None:
        test.skipTest("ffmpeg is not available")
    return exe


def _run_ffmpeg(test: unittest.TestCase, args: list[str]) -> None:
    exe = _ffmpeg_or_skip(test)
    completed = subprocess.run(
        [str(exe), "-y", "-hide_banner", "-loglevel", "error", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=CREATE_NO_WINDOW,
        stdin=subprocess.DEVNULL,
    )
    if completed.returncode != 0:
        test.fail(completed.stderr or completed.stdout)


def _make_clip(test: unittest.TestCase, path: Path, seconds: int = 2) -> None:
    _run_ffmpeg(
        test,
        [
            "-f",
            "lavfi",
            "-i",
            f"testsrc=size=160x120:rate=25:duration={seconds}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=880:duration={seconds}",
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(path),
        ],
    )


class ParseTests(unittest.TestCase):
    def test_safe_name_removes_windows_punctuation(self) -> None:
        self.assertEqual(safe_name('a:b*c?'), "a b c")
        self.assertEqual(safe_name("   "), "未命名")

    def test_entry_title_adds_part_once(self) -> None:
        titled = title_from_entry({"title": "测试标题", "page_data": {"part": "第一话"}}, "文件夹")
        self.assertEqual(titled, "测试标题 第一话")
        again = title_from_entry({"title": "测试标题 第一话", "page_data": {"part": "第一话"}}, "文件夹")
        self.assertEqual(again, "测试标题 第一话")

    def test_bilibili_url_is_not_a_file(self) -> None:
        paths, notice = parse_dropped_text("https://www.bilibili.com/video/BV1xx411c7mD")
        self.assertEqual(paths, [])
        self.assertIn("不会从网站下载", notice or "")

    def test_clipboard_path_must_exist(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "clip.mp4"
            target.write_bytes(b"demo")
            paths, notice = parse_dropped_text(f'"{target}"')
        self.assertIsNone(notice)
        self.assertEqual(paths, [target])

    def test_cache_folder_pairs_video_and_audio(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "video.m4s").write_bytes(b"video")
            (root / "audio.m4s").write_bytes(b"audio-bigger")
            (root / "entry.json").write_text(
                json.dumps({"title": "测试标题", "page_data": {"part": "第一话"}}, ensure_ascii=False),
                encoding="utf-8",
            )
            items = ingest_paths([root])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].kind, Kind.BILI)
        self.assertEqual(items[0].title, "测试标题 第一话")
        self.assertEqual(len(items[0].videos), 1)
        self.assertEqual(len(items[0].audios), 1)

    def test_numeric_flv_segments_stay_together(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "0.flv").write_bytes(b"a")
            (root / "1.flv").write_bytes(b"b")
            (root / "extra.mp4").write_bytes(b"c")
            items = classify_folder(root, list(root.iterdir()))
        kinds = sorted((item.kind, len(item.videos)) for item in items)
        self.assertIn((Kind.BILI, 2), kinds)
        self.assertIn((Kind.VIDEO, 1), kinds)

    def test_repair_strips_bytes_before_ftyp(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "video.m4s"
            payload = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 16
            source.write_bytes(b"junkhead!" + payload)
            self.assertGreater(container_start(source.read_bytes()), 0)
            repaired = repaired_path(source, root / "work")
            self.assertEqual(repaired.read_bytes()[:8], payload[:8])

    def test_report_states_what_it_is(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "总结.md"
            item = ingest_paths([])
            from pianzhuang.models import MediaItem

            media = MediaItem.new("样例", Kind.VIDEO, videos=[Path(folder) / "a.mp4"])
            build_report(
                media,
                {"duration": 2, "width": 160, "height": 120, "fps": 25, "vcodec": "h264", "acodec": "aac", "size": 10},
                {"mean": "-20.0 dB"},
                [0.4],
                None,
                destination,
            )
            text = destination.read_text(encoding="utf-8")
        self.assertIn("不是对口播或剧情的文字摘要", text)
        self.assertIn("160×120", text)
        self.assertIn("-20.0 dB", text)
        self.assertEqual(item, [])


class FFmpegTests(unittest.TestCase):
    def test_bilibili_pair_with_junk_header_becomes_mp4(self) -> None:
        _ffmpeg_or_skip(self)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            clip = root / "clip.mp4"
            _make_clip(self, clip, 2)
            cache = root / "cache"
            cache.mkdir()
            video = cache / "video.m4s"
            audio = cache / "audio.m4s"
            _run_ffmpeg(self, ["-i", str(clip), "-c:v", "copy", "-an", "-f", "mp4", str(video)])
            _run_ffmpeg(self, ["-i", str(clip), "-c:a", "copy", "-vn", "-f", "mp4", str(audio)])
            for path in (video, audio):
                path.write_bytes(b"junkhead!" + path.read_bytes())
            (cache / "entry.json").write_text(
                json.dumps({"title": "缓存测试", "page_data": {"part": "P1"}}, ensure_ascii=False),
                encoding="utf-8",
            )
            items = ingest_paths([cache])
            output = root / "out"
            results = convert_items(
                items,
                Settings(output_dir=output, preset="快速封装", container="MP4"),
                lambda _message: None,
                lambda _fraction: None,
                threading.Event(),
                lambda *_args: None,
            )
            self.assertTrue(results[0].ok, results[0].message)
            info = probe_media(results[0].output)
        self.assertIsNotNone(info)
        assert info is not None
        self.assertTrue(info.has_video)
        self.assertTrue(info.has_audio)
        self.assertGreater(info.duration, 1.5)
        self.assertLess(info.duration, 2.6)
        self.assertEqual(info.vcodec, "h264")

    def test_standard_convert_audio_and_summary(self) -> None:
        _ffmpeg_or_skip(self)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            clip = root / "样例.mp4"
            _make_clip(self, clip, 2)
            output = root / "out"
            items = ingest_paths([clip])
            cancel = threading.Event()
            silent = lambda *_args: None
            converted = convert_items(
                items,
                Settings(output_dir=output, preset="标准", container="MP4"),
                silent,
                silent,
                cancel,
                silent,
            )
            audio = audio_items(items, Settings(output_dir=output, audio_format="M4A"), silent, silent, cancel, silent)
            summary = summary_items(items, Settings(output_dir=output), silent, silent, cancel, silent)
            self.assertTrue(converted[0].ok, converted[0].message)
            self.assertTrue(audio[0].ok, audio[0].message)
            self.assertTrue(summary[0].ok, summary[0].message)
            info = probe_media(converted[0].output)
            audio_info = probe_media(audio[0].output)
            report = summary[0].output.read_text(encoding="utf-8")
            sheet = summary[0].output.parent / "storyboard.jpg"
            self.assertEqual(info.vcodec, "h264")
            self.assertTrue(audio_info.has_audio)
            self.assertGreater(audio[0].output.stat().st_size, 500)
            self.assertIn("样例", report)
            self.assertIn("h264", report)
            self.assertTrue(sheet.is_file())
            self.assertGreater(sheet.stat().st_size, 500)

    def test_flv_segments_concat(self) -> None:
        _ffmpeg_or_skip(self)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ("0.flv", "1.flv"):
                _make_clip(self, root / name, 1)
            (root / "entry.json").write_text(json.dumps({"title": "分段"}), encoding="utf-8")
            items = ingest_paths([root])
            self.assertEqual(len(items), 1)
            self.assertEqual(len(items[0].videos), 2)
            results = convert_items(
                items,
                Settings(output_dir=root / "out", preset="快速封装", container="MP4"),
                lambda _message: None,
                lambda _fraction: None,
                threading.Event(),
                lambda *_args: None,
            )
            self.assertTrue(results[0].ok, results[0].message)
            info = probe_media(results[0].output)
            self.assertGreater(info.duration, 1.5)

    def test_cli_convert(self) -> None:
        _ffmpeg_or_skip(self)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            clip = root / "cli.mp4"
            _make_clip(self, clip, 1)
            code = main(["--convert", str(clip), "-o", str(root / "out"), "--preset", "快速封装", "--container", "MP4"])
            produced = list((root / "out").glob("*.mp4"))
        self.assertEqual(code, 0)
        self.assertEqual(len(produced), 1)

    def test_sendto_shortcut_can_be_written(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            link = Path(folder) / "光影工坊.lnk"
            install_sendto(link)
            self.assertGreater(link.stat().st_size, 100)


class WindowTests(unittest.TestCase):
    def test_window_opens(self) -> None:
        import tkinter as tk

        try:
            from pianzhuang.app import App

            app = App([])
        except tk.TclError as exc:
            self.skipTest(str(exc))
        try:
            app.update()
            self.assertEqual(app.title(), "光影工坊")
        finally:
            app.destroy()


if __name__ == "__main__":
    unittest.main()
