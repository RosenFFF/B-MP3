"""命令行入口。不带参数时打开窗口。"""

from __future__ import annotations

import argparse
import sys
import threading
from pathlib import Path

from pianzhuang.config import load_settings
from pianzhuang.ingest import ingest_paths
from pianzhuang.jobs import audio_items, convert_items, summary_items
from pianzhuang.models import AUDIO_FORMATS, CONTAINERS, PRESETS, Settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="光影工坊",
        description="把本机视频和 B 站客户端缓存转为 MP4、音频或视频总结。",
    )
    parser.add_argument("--import", nargs="*", dest="imports", help="打开窗口并导入这些路径")
    parser.add_argument("--convert", action="store_true", help="转为 MP4、MKV 或 MOV")
    parser.add_argument("--audio", action="store_true", help="提取音频")
    parser.add_argument("--summary", action="store_true", help="生成视频总结")
    parser.add_argument("--preset", choices=PRESETS)
    parser.add_argument("--container", choices=CONTAINERS)
    parser.add_argument("--format", dest="audio_format", choices=AUDIO_FORMATS)
    parser.add_argument("-o", "--output")
    parser.add_argument("files", nargs="*")
    args = parser.parse_args(argv)

    modes = sum(bool(flag) for flag in (args.convert, args.audio, args.summary))
    if modes > 1:
        print("一次只能做一种处理。", file=sys.stderr)
        return 2
    if modes == 1:
        return _headless(args)

    paths = list(args.imports or [])
    paths.extend(args.files)
    from pianzhuang.app import run_app

    run_app(paths)
    return 0


def _headless(args) -> int:
    saved = load_settings()
    output = Path(args.output or saved["output_dir"])
    settings = Settings(
        output_dir=output,
        preset=args.preset or saved["preset"],
        container=args.container or saved["container"],
        audio_format=args.audio_format or saved["audio_format"],
    )
    if not args.files:
        print("请在命令后面写上文件或文件夹。", file=sys.stderr)
        return 2
    items = ingest_paths(args.files)
    if not items:
        print("没有找到可处理的视频或音频。", file=sys.stderr)
        return 2
    cancel = threading.Event()

    def log(message: str) -> None:
        print(message, flush=True)

    def on_progress(_fraction: float) -> None:
        return None

    def on_item(item, status: str, detail: str | None = None) -> None:
        print(f"{status}：{item.title}" + (f" {detail}" if detail else ""), flush=True)

    if args.convert:
        results = convert_items(items, settings, log, on_progress, cancel, on_item)
    elif args.audio:
        results = audio_items(items, settings, log, on_progress, cancel, on_item)
    else:
        results = summary_items(items, settings, log, on_progress, cancel, on_item)
    failed = False
    for result in results:
        if result.output:
            print(result.output)
        if not result.ok:
            failed = True
            if result.message and not result.cancelled:
                print(result.message, file=sys.stderr)
    return 1 if failed else 0
