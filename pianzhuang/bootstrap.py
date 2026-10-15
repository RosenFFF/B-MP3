"""下载或解压程序自带的 FFmpeg。"""

from __future__ import annotations

import sys

from pianzhuang.binaries import ensure_ffmpeg, ffmpeg_version_line


def main() -> int:
    def log(message: str) -> None:
        print(message, flush=True)

    try:
        path = ensure_ffmpeg(download=True, log=log)
    except Exception as exc:  # noqa: BLE001 - 安装脚本需要看到失败原因
        print(str(exc), file=sys.stderr)
        return 1
    version = ffmpeg_version_line()
    print(version or path)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
