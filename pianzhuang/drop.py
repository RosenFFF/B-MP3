"""Windows 原生 64 位安全文件拖放支持。
替代存在 64 位指针截断 (Access Violation 0xC0000005) 隐患的 windnd 库，
支持全窗口及所有子控件无缝拖拽文件与文件夹。
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import sys
from pathlib import Path
from typing import Callable

user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32

LRESULT = ctypes.c_int64 if sys.maxsize > 2**32 else ctypes.c_long
WPARAM = ctypes.c_uint64 if sys.maxsize > 2**32 else ctypes.c_uint
LPARAM = ctypes.c_int64 if sys.maxsize > 2**32 else ctypes.c_long
UINT = ctypes.c_uint32
HWND = wintypes.HWND

WNDPROC = ctypes.WINFUNCTYPE(LRESULT, HWND, UINT, WPARAM, LPARAM)

GWLP_WNDPROC = -4
WM_DROPFILES = 0x0233

if sys.maxsize > 2**32:
    GetWindowLongPtr = user32.GetWindowLongPtrW
    GetWindowLongPtr.restype = ctypes.c_void_p
    GetWindowLongPtr.argtypes = [HWND, ctypes.c_int]

    SetWindowLongPtr = user32.SetWindowLongPtrW
    SetWindowLongPtr.restype = ctypes.c_void_p
    SetWindowLongPtr.argtypes = [HWND, ctypes.c_int, ctypes.c_void_p]
else:
    GetWindowLongPtr = user32.GetWindowLongW
    GetWindowLongPtr.restype = ctypes.c_void_p
    GetWindowLongPtr.argtypes = [HWND, ctypes.c_int]

    SetWindowLongPtr = user32.SetWindowLongW
    SetWindowLongPtr.restype = ctypes.c_void_p
    SetWindowLongPtr.argtypes = [HWND, ctypes.c_int, ctypes.c_void_p]

CallWindowProc = user32.CallWindowProcW
CallWindowProc.restype = LRESULT
CallWindowProc.argtypes = [ctypes.c_void_p, HWND, UINT, WPARAM, LPARAM]

DragAcceptFiles = shell32.DragAcceptFiles
DragAcceptFiles.restype = None
DragAcceptFiles.argtypes = [HWND, wintypes.BOOL]

DragQueryFileW = shell32.DragQueryFileW
DragQueryFileW.restype = UINT
DragQueryFileW.argtypes = [ctypes.c_void_p, UINT, wintypes.LPWSTR, UINT]

DragFinish = shell32.DragFinish
DragFinish.restype = None
DragFinish.argtypes = [ctypes.c_void_p]


class DropManager:
    def __init__(self, root_window, on_drop: Callable[[list[Path]], None]) -> None:
        self.root = root_window
        self.on_drop = on_drop
        self.old_wnd_procs: dict[int, int] = {}
        self.c_procs: dict[int, WNDPROC] = {}

    def _create_proc(self, hwnd_val: int) -> WNDPROC:
        def proc(h, msg, wp, lp):
            if msg == WM_DROPFILES:
                try:
                    count = DragQueryFileW(wp, 0xFFFFFFFF, None, 0)
                    files: list[Path] = []
                    # 1024 字符缓冲区，满足 Windows 长路径
                    buf = ctypes.create_unicode_buffer(1024)
                    for i in range(count):
                        length = DragQueryFileW(wp, i, buf, 1024)
                        if length > 0:
                            files.append(Path(buf.value))
                    DragFinish(wp)
                    if files:
                        self.root.after(0, lambda f=files: self.on_drop(f))
                except Exception:
                    pass
                # 处理完 WM_DROPFILES 必须返回 0，严禁传给旧 WndProc
                return 0

            old = self.old_wnd_procs.get(h)
            if old:
                return CallWindowProc(old, h, msg, wp, lp)
            return user32.DefWindowProcW(h, msg, wp, lp)

        return WNDPROC(proc)

    def hook_widget(self, widget) -> None:
        try:
            h = widget.winfo_id()
            if h and h not in self.old_wnd_procs:
                DragAcceptFiles(h, True)
                old = GetWindowLongPtr(h, GWLP_WNDPROC)
                if old:
                    self.old_wnd_procs[h] = old
                    p = self._create_proc(h)
                    self.c_procs[h] = p
                    SetWindowLongPtr(h, GWLP_WNDPROC, ctypes.cast(p, ctypes.c_void_p))
        except Exception:
            pass

        try:
            for child in widget.winfo_children():
                self.hook_widget(child)
        except Exception:
            pass

    def hook(self) -> None:
        self.hook_widget(self.root)
