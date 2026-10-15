"""把光影工坊加进资源管理器的「发送到」菜单。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from pianzhuang.binaries import CREATE_NO_WINDOW, ROOT


def sendto_link_path() -> Path:
    appdata = os.environ.get("APPDATA", str(Path.home()))
    return Path(appdata) / "Microsoft" / "Windows" / "SendTo" / "光影工坊.lnk"


def pythonw_path() -> Path:
    candidate = Path(sys.executable).with_name("pythonw.exe")
    return candidate if candidate.is_file() else Path(sys.executable)


def install_sendto(link_path: Path | None = None) -> Path:
    link = link_path or sendto_link_path()
    link.parent.mkdir(parents=True, exist_ok=True)

    if getattr(sys, "frozen", False):
        target = str(Path(sys.executable))
        arguments = "--import"
        work_dir = str(Path(sys.executable).parent)
        icon_loc = str(Path(sys.executable))
    else:
        main_py = ROOT / "main.py"
        target = str(pythonw_path())
        arguments = f'"{main_py}" --import'
        work_dir = str(ROOT)
        ico = ROOT / "resources" / "icon.ico"
        icon_loc = str(ico) if ico.is_file() else target

    lines = [
        "$ws = New-Object -ComObject WScript.Shell",
        f"$s = $ws.CreateShortcut({_ps_quote(str(link))})",
        f"$s.TargetPath = {_ps_quote(target)}",
        f"$s.Arguments = {_ps_quote(arguments)}",
        f"$s.WorkingDirectory = {_ps_quote(work_dir)}",
        f"$s.IconLocation = {_ps_quote(icon_loc)}",
        "$s.Description = '用光影工坊导入视频'",
        "$s.Save()",
    ]
    script = "\n".join(lines)
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=CREATE_NO_WINDOW,
        stdin=subprocess.DEVNULL,
        check=False,
    )
    if completed.returncode != 0 or not link.is_file():
        detail = (completed.stderr or completed.stdout or "无法创建快捷方式").strip()
        raise RuntimeError(detail)
    return link


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
