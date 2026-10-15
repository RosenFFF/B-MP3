"""光影工坊的主窗口。"""

from __future__ import annotations

import os
import queue
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image

from pianzhuang import __version__
from pianzhuang.binaries import ROOT, ensure_ffmpeg, ffmpeg_path, ffmpeg_version_line
from pianzhuang.config import append_log, default_output, load_settings, save_settings
from pianzhuang.ingest import default_bili_roots, describe_item, ingest_paths, parse_dropped_text
from pianzhuang.jobs import audio_items, convert_items, summary_items
from pianzhuang.media import available_audio_formats, encoder_text, probe_media
from pianzhuang.models import AUDIO_FORMATS, CONTAINERS, PRESETS, Kind, MediaItem, Settings
from pianzhuang.sendto import install_sendto, sendto_link_path
from pianzhuang.drop import DropManager

BG = "#141613"
PANEL = "#1E211C"
PANEL_2 = "#262A24"
INK = "#F3F0E6"
MUTED = "#A39E90"
LINE = "#34382F"
ACCENT = "#E0A04A"
ACCENT_HOVER = "#C98A34"
ACCENT_TEXT = "#1C1408"
SAGE = "#8FB08A"
DANGER = "#D06A5A"
DROP = "#1A1E18"

BADGE_BG = {
    Kind.VIDEO: "#2C3A2C",
    Kind.AUDIO: "#3A3424",
    Kind.BILI: "#3A2E24",
}
BADGE_FG = {
    Kind.VIDEO: "#D5E7D2",
    Kind.AUDIO: "#F0E2C0",
    Kind.BILI: "#F3D7B8",
}
KIND_TEXT = {Kind.VIDEO: "视频", Kind.AUDIO: "音频", Kind.BILI: "缓存"}
STATUS_COLOR = {
    "等待": MUTED,
    "处理中": ACCENT,
    "完成": SAGE,
    "失败": DANGER,
    "已取消": MUTED,
}
FILE_TYPES = [
    ("媒体文件", "*.mp4 *.mkv *.flv *.blv *.avi *.mov *.wmv *.webm *.ts *.m4v *.m4s *.mpg *.mpeg *.mp3 *.m4a *.wav *.aac *.flac *.ogg"),
    ("所有文件", "*.*"),
]


class App(ctk.CTk):
    def __init__(self, initial_paths: list[Path] | None = None) -> None:
        super().__init__()
        self.title("光影工坊")
        self.geometry("1120x760")
        self.minsize(980, 680)
        self.configure(fg_color=BG)
        self._set_app_icon()

        self.font_title = ctk.CTkFont(family="Microsoft YaHei UI", size=28, weight="bold")
        self.font_sub = ctk.CTkFont(family="Microsoft YaHei UI", size=13)
        self.font_body = ctk.CTkFont(family="Microsoft YaHei UI", size=14)
        self.font_small = ctk.CTkFont(family="Microsoft YaHei UI", size=12)
        self.font_button = ctk.CTkFont(family="Microsoft YaHei UI", size=14, weight="bold")

        saved = load_settings()
        self.output_var = tk.StringVar(value=saved["output_dir"])
        self.preset_var = tk.StringVar(value=saved["preset"])
        self.container_var = tk.StringVar(value=saved["container"])
        self.audio_var = tk.StringVar(value=saved["audio_format"])
        self.count_var = tk.StringVar(value="0 个")
        self.progress_var = tk.StringVar(value="准备好了")

        self.items: list[MediaItem] = []
        self.rows: dict[str, dict] = {}
        self.known: set[tuple[str, ...]] = set()
        self.busy = False
        self.cancel_event = threading.Event()
        self.probe_queue: queue.Queue[MediaItem] = queue.Queue()
        self._last_progress = 0.0
        self._note = "准备好了"
        self._drop_hooked = False

        self._build()
        self.container_var.trace_add("write", lambda *_: self._sync_convert_label())
        self._sync_convert_label()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Control-o>", self._on_open_key)
        self.bind("<Control-O>", self._on_open_key)
        self.bind("<Control-v>", self._on_paste_key)
        self.bind("<Control-V>", self._on_paste_key)

        threading.Thread(target=self._probe_loop, daemon=True).start()
        self.after(250, self._hook_drop)
        self.after(400, self._announce_ffmpeg)
        if initial_paths:
            self.after(200, lambda: self.add_paths(initial_paths))

    def _find_resource(self, filename: str) -> Path | None:
        candidates = []
        if hasattr(sys, "_MEIPASS"):
            candidates.append(Path(sys._MEIPASS) / "resources" / filename)
        exe_dir = Path(sys.executable).parent
        candidates.append(exe_dir / "resources" / filename)
        candidates.append(ROOT / "resources" / filename)
        for c in candidates:
            if c.is_file():
                return c
        return None

    def _set_app_icon(self) -> None:
        ico = self._find_resource("icon.ico")
        if ico:
            try:
                self.iconbitmap(str(ico))
                return
            except Exception:
                pass
        png = self._find_resource("icon.png")
        if png:
            try:
                img = tk.PhotoImage(file=str(png))
                self.iconphoto(True, img)
            except Exception:
                pass

    def _load_logo_image(self) -> ctk.CTkImage | None:
        png = self._find_resource("icon.png")
        if png:
            try:
                pil_img = Image.open(png)
                return ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(42, 42))
            except Exception:
                return None
        return None

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 4))
        header.grid_columnconfigure(1, weight=1)

        self._logo_image = self._load_logo_image()
        if self._logo_image:
            logo_label = ctk.CTkLabel(header, text="", image=self._logo_image)
            logo_label.grid(row=0, column=0, rowspan=2, padx=(0, 12), sticky="w")

        ctk.CTkLabel(header, text="光影工坊", font=self.font_title, text_color=INK, anchor="w").grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(
            header,
            text=f"音视频转码与 B 站缓存处理工坊  ·  v{__version__}",
            font=self.font_sub,
            text_color=MUTED,
            anchor="w",
        ).grid(row=1, column=1, sticky="w", pady=(2, 0))
        self.ff_button = ctk.CTkButton(
            header,
            text="正在检查 FFmpeg",
            width=150,
            height=32,
            corner_radius=16,
            fg_color=PANEL_2,
            hover_color=LINE,
            text_color=MUTED,
            font=self.font_small,
            command=self._on_ff_click,
        )
        self.ff_button.grid(row=0, column=2, rowspan=2, padx=(12, 0))

        body = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        body.grid(row=1, column=0, sticky="nsew", padx=12, pady=8)
        body.grid_columnconfigure(0, minsize=320, weight=0)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(body, fg_color=PANEL, corner_radius=18)
        left.grid(row=0, column=0, sticky="nsew", padx=(8, 6), pady=4)
        right = ctk.CTkFrame(body, fg_color=PANEL, corner_radius=18)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 8), pady=4)
        self._build_import(left)
        self._build_queue(right)
        self._build_bottom()

    def _build_import(self, parent) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(3, weight=1)

        drop = ctk.CTkFrame(parent, fg_color=DROP, border_width=1, border_color=ACCENT, corner_radius=16, height=168)
        drop.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 10))
        drop.grid_propagate(False)
        drop.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(drop, text="把视频拖进窗口", font=self.font_button, text_color=INK).grid(row=0, column=0, pady=(28, 2))
        ctk.CTkLabel(drop, text="文件、文件夹、B 站缓存都可以", font=self.font_small, text_color=MUTED).grid(row=1, column=0)
        ctk.CTkLabel(drop, text="点这里选择文件", font=self.font_small, text_color=ACCENT).grid(row=2, column=0, pady=(10, 0))
        self._bind_tree(drop, lambda _event: self.pick_files())

        actions = ctk.CTkFrame(parent, fg_color="transparent")
        actions.grid(row=1, column=0, sticky="ew", padx=12, pady=4)
        actions.grid_columnconfigure((0, 1), weight=1)
        buttons = [
            ("选择文件", self.pick_files),
            ("选择文件夹", self.pick_folder),
            ("粘贴路径", self.paste_paths),
            ("扫描 B 站缓存", self.scan_bili),
        ]
        for index, (text, command) in enumerate(buttons):
            button = ctk.CTkButton(
                actions,
                text=text,
                command=command,
                height=40,
                corner_radius=10,
                fg_color=PANEL_2,
                hover_color=LINE,
                text_color=INK,
                font=self.font_body,
            )
            button.grid(row=index // 2, column=index % 2, sticky="ew", padx=4, pady=4)

        self.sendto_btn = ctk.CTkButton(
            parent,
            text="已在「发送到」里" if sendto_link_path().is_file() else "添加到「发送到」",
            command=self.on_sendto,
            height=36,
            corner_radius=10,
            fg_color="transparent",
            border_width=1,
            border_color=LINE,
            hover_color=PANEL_2,
            text_color=INK,
            font=self.font_small,
        )
        self.sendto_btn.grid(row=2, column=0, sticky="ew", padx=16, pady=(8, 4))

        hint = ctk.CTkFrame(parent, fg_color="transparent")
        hint.grid(row=3, column=0, sticky="sew", padx=18, pady=(8, 16))
        for text in (
            "Ctrl+O  选择文件",
            "Ctrl+Shift+O  选择文件夹",
            "Ctrl+V  粘贴路径",
            "也可以把文件拖到「启动光影工坊.bat」或快捷方式上。",
            "MP4、MKV、FLV、WEBM、M4S、BLV 都能进队列。",
            "B 站部分只认客户端已经下载的缓存，不会打开网页下载。",
        ):
            ctk.CTkLabel(hint, text=text, font=self.font_small, text_color=MUTED, anchor="w").pack(anchor="w", pady=1)

    def _build_queue(self, parent) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)
        bar = ctk.CTkFrame(parent, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 6))
        bar.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(bar, text="队列", font=self.font_button, text_color=INK, anchor="w").grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(bar, textvariable=self.count_var, font=self.font_small, text_color=MUTED).grid(row=0, column=1, padx=8)
        self.clear_btn = ctk.CTkButton(
            bar,
            text="清空",
            width=64,
            height=28,
            fg_color="transparent",
            hover_color=LINE,
            text_color=MUTED,
            font=self.font_small,
            command=self.clear_items,
        )
        self.clear_btn.grid(row=0, column=2)

        self.stack = ctk.CTkFrame(parent, fg_color="transparent")
        self.stack.grid(row=1, column=0, sticky="nsew", padx=10, pady=4)
        self.stack.grid_columnconfigure(0, weight=1)
        self.stack.grid_rowconfigure(0, weight=1)
        self.empty = ctk.CTkLabel(
            self.stack,
            text="还没有文件\n从左侧导入，或把文件拖进窗口",
            font=self.font_body,
            text_color=MUTED,
            justify="center",
        )
        self.empty.grid(row=0, column=0)
        self.queue = ctk.CTkScrollableFrame(self.stack, fg_color="transparent")
        self.queue.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(parent, text="记录", font=self.font_small, text_color=MUTED, anchor="w").grid(
            row=2, column=0, sticky="w", padx=18, pady=(4, 0)
        )
        self.logbox = ctk.CTkTextbox(
            parent,
            height=118,
            fg_color=PANEL_2,
            text_color=INK,
            font=self.font_small,
            corner_radius=12,
            wrap="word",
        )
        self.logbox.grid(row=3, column=0, sticky="ew", padx=14, pady=(4, 14))

    def _build_bottom(self) -> None:
        bottom = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=0)
        bottom.grid(row=2, column=0, sticky="ew")
        bottom.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(bottom, text="输出", font=self.font_small, text_color=MUTED).grid(row=0, column=0, padx=(18, 8), pady=(14, 6))
        entry = ctk.CTkEntry(
            bottom,
            textvariable=self.output_var,
            height=36,
            fg_color=PANEL_2,
            border_color=LINE,
            text_color=INK,
            font=self.font_body,
        )
        entry.grid(row=0, column=1, sticky="ew", pady=(14, 6))
        ctk.CTkButton(
            bottom, text="浏览", width=72, height=36, fg_color=PANEL_2, hover_color=LINE, text_color=INK, font=self.font_small, command=self.pick_output
        ).grid(row=0, column=2, padx=6, pady=(14, 6))
        ctk.CTkButton(
            bottom, text="打开", width=72, height=36, fg_color=PANEL_2, hover_color=LINE, text_color=INK, font=self.font_small, command=self.open_output
        ).grid(row=0, column=3, padx=(0, 16), pady=(14, 6))

        options = ctk.CTkFrame(bottom, fg_color="transparent")
        options.grid(row=1, column=0, columnspan=4, sticky="ew", padx=14, pady=(2, 4))
        options.grid_columnconfigure(6, weight=1)
        self.preset_menu = self._menu(options, "画质", self.preset_var, list(PRESETS), 0)
        self.container_menu = self._menu(options, "容器", self.container_var, list(CONTAINERS), 2)
        self.audio_menu = self._menu(options, "音频", self.audio_var, self._audio_choices(), 4)

        buttons = ctk.CTkFrame(options, fg_color="transparent")
        buttons.grid(row=0, column=7, sticky="e")
        self.convert_btn = ctk.CTkButton(
            buttons,
            text="转为 MP4",
            width=120,
            height=40,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            text_color=ACCENT_TEXT,
            font=self.font_button,
            command=self.on_convert,
        )
        self.convert_btn.grid(row=0, column=0, padx=4)
        self.audio_btn = ctk.CTkButton(
            buttons,
            text="提取音频",
            width=110,
            height=40,
            fg_color=PANEL_2,
            hover_color=LINE,
            text_color=INK,
            font=self.font_button,
            command=self.on_audio,
        )
        self.audio_btn.grid(row=0, column=1, padx=4)
        self.summary_btn = ctk.CTkButton(
            buttons,
            text="视频总结",
            width=110,
            height=40,
            fg_color=PANEL_2,
            hover_color=LINE,
            text_color=INK,
            font=self.font_button,
            command=self.on_summary,
        )
        self.summary_btn.grid(row=0, column=2, padx=4)
        self.stop_btn = ctk.CTkButton(
            buttons,
            text="停止",
            width=72,
            height=40,
            fg_color=LINE,
            hover_color=DANGER,
            text_color=MUTED,
            font=self.font_button,
            state="disabled",
            command=self.on_stop,
        )
        self.stop_btn.grid(row=0, column=3, padx=(4, 2))

        self.progress = ctk.CTkProgressBar(bottom, height=8, fg_color=LINE, progress_color=ACCENT)
        self.progress.grid(row=2, column=0, columnspan=4, sticky="ew", padx=18, pady=(8, 0))
        self.progress.set(0)
        ctk.CTkLabel(bottom, textvariable=self.progress_var, font=self.font_small, text_color=MUTED, anchor="w").grid(
            row=3, column=0, columnspan=4, sticky="w", padx=18, pady=(4, 12)
        )

    def _menu(self, parent, label: str, variable: tk.StringVar, values: list[str], column: int):
        ctk.CTkLabel(parent, text=label, font=self.font_small, text_color=MUTED).grid(row=0, column=column, padx=(4, 4))
        menu = ctk.CTkOptionMenu(
            parent,
            variable=variable,
            values=values,
            width=118,
            height=36,
            fg_color=PANEL_2,
            button_color=LINE,
            button_hover_color=ACCENT,
            dropdown_fg_color=PANEL,
            dropdown_hover_color=LINE,
            text_color=INK,
            font=self.font_small,
        )
        menu.grid(row=0, column=column + 1, padx=(0, 8))
        return menu

    def _audio_choices(self) -> list[str]:
        choices = available_audio_formats()
        if self.audio_var.get() not in choices:
            self.audio_var.set(choices[0])
        return choices

    def _sync_convert_label(self) -> None:
        self.convert_btn.configure(text=f"转为 {self.container_var.get()}")

    def _bind_tree(self, widget, callback) -> None:
        widget.bind("<Button-1>", callback)
        try:
            widget.configure(cursor="hand2")
        except tk.TclError:
            pass
        for child in widget.winfo_children():
            self._bind_tree(child, callback)

    def _hook_drop(self) -> None:
        if self._drop_hooked or not self.winfo_exists():
            return
        try:
            self._drop_manager = DropManager(self, self.add_paths)
            self._drop_manager.hook()
            self._drop_hooked = True
        except Exception as exc:  # noqa: BLE001 - 拖放失败时其他入口仍然可用
            self.log(f"拖放不可用：{exc}")

    def _on_drop(self, files) -> None:
        paths: list[Path] = []
        for item in files:
            if isinstance(item, bytes):
                item = os.fsdecode(item)
            paths.append(Path(item))
        self.after(0, lambda: self.add_paths(paths))

    def _announce_ffmpeg(self) -> None:
        if ffmpeg_path():
            version = ffmpeg_version_line() or "FFmpeg 已就绪"
            self._set_ff(version.split(" ", 1)[-1] if version.lower().startswith("ffmpeg") else "FFmpeg 已就绪", True)
            self.log(version)
            return
        self._set_ff("未找到 FFmpeg", False)
        self.log("还没有 FFmpeg。点右上角可以下载到程序目录。")

    def _set_ff(self, text: str, ready: bool) -> None:
        self.ff_button.configure(text=text[:28], text_color=SAGE if ready else DANGER)

    def _on_ff_click(self) -> None:
        if ffmpeg_path():
            self.log(ffmpeg_version_line() or "FFmpeg 已就绪")
            return
        self._offer_ffmpeg()

    def _offer_ffmpeg(self) -> None:
        agreed = messagebox.askyesno(
            "需要 FFmpeg",
            "光影工坊用 FFmpeg 完成转换、提取和总结。\n现在下载到程序目录吗？大约 80MB，只需一次。",
            parent=self,
        )
        if agreed:
            self._download_ffmpeg()

    def _download_ffmpeg(self) -> None:
        if self.busy:
            return
        self.busy = True
        self._set_busy(True)
        self._note = "正在下载 FFmpeg"
        self.progress.configure(mode="indeterminate")
        self.progress.start()
        self.progress_var.set("正在下载 FFmpeg…")

        def work() -> None:
            try:
                path = ensure_ffmpeg(download=True, log=self.log)
                encoder_text(refresh=True)
                error = None
                message = f"FFmpeg 已就绪：{path}"
            except Exception as exc:  # noqa: BLE001
                error = str(exc)
                message = ""

            def done() -> None:
                self.progress.stop()
                self.progress.configure(mode="determinate")
                self.progress.set(0)
                self.busy = False
                self._set_busy(False)
                if error:
                    self.progress_var.set("FFmpeg 下载失败")
                    messagebox.showerror("下载失败", error, parent=self)
                    return
                self._set_ff("FFmpeg 已就绪", True)
                self.audio_menu.configure(values=self._audio_choices())
                self.progress_var.set("FFmpeg 已就绪")
                self.log(message)

            self.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def pick_files(self) -> None:
        names = filedialog.askopenfilenames(title="选择视频或音频", filetypes=FILE_TYPES, parent=self)
        if names:
            self.add_paths([Path(name) for name in names])

    def pick_folder(self, title: str = "选择文件夹") -> None:
        folder = filedialog.askdirectory(title=title, parent=self)
        if folder:
            self.add_paths([Path(folder)])

    def paste_paths(self) -> None:
        try:
            text = self.clipboard_get()
        except tk.TclError:
            self.log("剪贴板是空的。")
            return
        paths, notice = parse_dropped_text(text)
        if notice:
            self.log(notice)
        if paths:
            self.add_paths(paths)

    def scan_bili(self) -> None:
        roots = default_bili_roots()
        if roots:
            preview = "\n".join(str(path) for path in roots[:6])
            answer = messagebox.askyesnocancel(
                "扫描 B 站缓存",
                "在这些位置发现可能的客户端目录：\n"
                + preview
                + "\n\n选“是”扫描这些目录。\n选“否”改成手动选择文件夹。",
                parent=self,
            )
            if answer is None:
                return
            if answer:
                self.add_paths(roots)
                return
        self.pick_folder("选择 B 站客户端的下载或缓存目录")

    def on_sendto(self) -> None:
        try:
            path = install_sendto()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("没有加入发送到", str(exc), parent=self)
            return
        self.sendto_btn.configure(text="已在「发送到」里")
        self.log(f"已加入系统「发送到」：{path}")
        messagebox.showinfo("已加入", "在资源管理器里右键文件，打开「发送到」，选择「光影工坊」。", parent=self)

    def add_paths(self, paths: list[Path]) -> None:
        existing = []
        missing = []
        for path in paths:
            candidate = Path(path).expanduser()
            if candidate.exists():
                existing.append(candidate)
            else:
                missing.append(str(candidate))
        try:
            items = ingest_paths(existing)
        except Exception as exc:  # noqa: BLE001
            self.log(f"导入失败：{exc}")
            return
        if len(items) > 300 and not messagebox.askyesno("文件很多", f"找到 {len(items)} 个，都加入队列吗？", parent=self):
            return
        added = 0
        for item in items:
            if item.key in self.known:
                continue
            self.known.add(item.key)
            self.items.append(item)
            self._add_row(item)
            self.probe_queue.put(item)
            added += 1
        self._sync_count()
        if added:
            skipped = len(items) - added
            message = f"已导入 {added} 个"
            if skipped:
                message += f"，跳过 {skipped} 个重复"
            self.log(message)
        elif not missing:
            self.log("没有找到可处理的视频或音频。")
        if missing:
            self.log("这些路径不存在：" + "；".join(missing[:5]))

    def _add_row(self, item: MediaItem) -> None:
        if not self.queue.winfo_ismapped():
            self.empty.grid_remove()
            self.queue.grid(row=0, column=0, sticky="nsew")
        row = ctk.CTkFrame(self.queue, fg_color=PANEL_2, corner_radius=12)
        row.pack(fill="x", pady=4, padx=2)
        row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            row,
            text=KIND_TEXT[item.kind],
            width=52,
            height=26,
            corner_radius=8,
            fg_color=BADGE_BG[item.kind],
            text_color=BADGE_FG[item.kind],
            font=self.font_small,
        ).grid(row=0, column=0, rowspan=2, padx=(10, 8), pady=10)
        title = ctk.CTkLabel(row, text=item.title, anchor="w", justify="left", font=self.font_body, text_color=INK)
        title.grid(row=0, column=1, sticky="ew", pady=(8, 0))
        meta = ctk.CTkLabel(row, text=item.detail or "正在读取…", anchor="w", justify="left", font=self.font_small, text_color=MUTED)
        meta.grid(row=1, column=1, sticky="ew", pady=(0, 8))
        status = ctk.CTkLabel(row, text=item.status, width=64, font=self.font_small, text_color=MUTED)
        status.grid(row=0, column=2, rowspan=2, padx=4)
        remove = ctk.CTkButton(
            row,
            text="移除",
            width=52,
            height=28,
            fg_color="transparent",
            hover_color=LINE,
            text_color=MUTED,
            font=self.font_small,
            command=lambda current=item: self.remove_item(current),
        )
        remove.grid(row=0, column=3, rowspan=2, padx=(0, 8))
        self.rows[item.id] = {"row": row, "title": title, "meta": meta, "status": status, "remove": remove}
        self._fit_titles()

    def _fit_titles(self) -> None:
        width = max(180, self.queue.winfo_width() - 190)
        for row in self.rows.values():
            row["title"].configure(wraplength=width)
            row["meta"].configure(wraplength=width)

    def remove_item(self, item: MediaItem) -> None:
        if self.busy or item.id not in self.rows:
            return
        self.rows.pop(item.id)["row"].destroy()
        self.items = [current for current in self.items if current.id != item.id]
        self.known.discard(item.key)
        self._sync_count()

    def clear_items(self) -> None:
        if self.busy:
            return
        for row in self.rows.values():
            row["row"].destroy()
        self.rows.clear()
        self.items.clear()
        self.known.clear()
        self._sync_count()

    def _sync_count(self) -> None:
        self.count_var.set(f"{len(self.items)} 个")
        if self.items:
            self.empty.grid_remove()
            if not self.queue.winfo_ismapped():
                self.queue.grid(row=0, column=0, sticky="nsew")
        else:
            self.queue.grid_remove()
            self.empty.grid(row=0, column=0)

    def _probe_loop(self) -> None:
        while True:
            item = self.probe_queue.get()
            path = item.primary_path()
            text = item.detail
            if path is not None:
                try:
                    text = describe_item(item, probe_media(path))
                except Exception:
                    text = item.detail or path.name
            self.after(0, lambda current=item, detail=text: self._apply_detail(current, detail))

    def _apply_detail(self, item: MediaItem, detail: str) -> None:
        item.detail = detail
        row = self.rows.get(item.id)
        if row and item.status == "等待":
            row["meta"].configure(text=detail)

    def pick_output(self) -> None:
        folder = filedialog.askdirectory(title="选择输出目录", parent=self)
        if folder:
            self.output_var.set(folder)

    def open_output(self) -> None:
        folder = Path(self.output_var.get().strip() or default_output())
        try:
            folder.mkdir(parents=True, exist_ok=True)
            os.startfile(folder)  # type: ignore[attr-defined]
        except OSError as exc:
            messagebox.showerror("打不开目录", str(exc), parent=self)

    def on_convert(self) -> None:
        self._start("convert")

    def on_audio(self) -> None:
        self._start("audio")

    def on_summary(self) -> None:
        self._start("summary")

    def on_stop(self) -> None:
        if not self.busy:
            return
        self.cancel_event.set()
        self.log("正在停止，当前这一条结束后就停。")

    def _start(self, mode: str) -> None:
        if self.busy:
            return
        if ffmpeg_path() is None:
            self._offer_ffmpeg()
            return
        if not self.items:
            self.log("队列是空的。先拖入文件，或使用左侧的导入。")
            return
        output = Path(self.output_var.get().strip() or default_output())
        try:
            output.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror("输出目录不可用", str(exc), parent=self)
            return
        self._save_settings()
        settings = Settings(
            output_dir=output,
            preset=self.preset_var.get(),
            container=self.container_var.get(),
            audio_format=self.audio_var.get(),
        )
        self.busy = True
        self.cancel_event.clear()
        self._set_busy(True)
        self.progress.set(0)
        self._note = "准备处理"
        self.progress_var.set(self._note)
        workers = {"convert": convert_items, "audio": audio_items, "summary": summary_items}
        threading.Thread(
            target=self._worker,
            args=(workers[mode], list(self.items), settings, mode),
            daemon=True,
        ).start()

    def _worker(self, worker, items: list[MediaItem], settings: Settings, mode: str) -> None:
        try:
            results = worker(items, settings, self.log, self._bridge_progress, self.cancel_event, self._bridge_item)
        except Exception as exc:  # noqa: BLE001
            self.log(f"出错：{exc}")
            results = []

        def finish() -> None:
            self.busy = False
            self._set_busy(False)
            cancelled = any(result.cancelled for result in results)
            ok = sum(1 for result in results if result.ok)
            bad = sum(1 for result in results if not result.ok and not result.cancelled)
            if cancelled:
                self.progress_var.set("已停止")
            else:
                self.progress.set(1 if results else 0)
                text = f"完成 {ok} 个"
                if bad:
                    text += f"，失败 {bad} 个"
                self.progress_var.set(text)
            if mode == "summary":
                reports = [result.output for result in results if result.ok and result.output]
                if reports:
                    self.show_summary(reports[-1], reports)

        self.after(0, finish)

    def _bridge_progress(self, fraction: float) -> None:
        now = time.monotonic()
        if fraction < 1 and now - self._last_progress < 0.1:
            return
        self._last_progress = now
        percent = int(max(0.0, min(1.0, fraction)) * 100)

        def apply() -> None:
            self.progress.set(max(0.0, min(1.0, fraction)))
            self.progress_var.set(f"{self._note}  {percent}%")

        self.after(0, apply)

    def _bridge_item(self, item: MediaItem, status: str, detail: str | None = None) -> None:
        def apply() -> None:
            item.status = status
            if status == "处理中":
                self._note = f"{status} · {item.title}"
                self.progress_var.set(self._note)
            row = self.rows.get(item.id)
            if row is None:
                return
            row["status"].configure(text=status, text_color=STATUS_COLOR.get(status, MUTED))
            if detail:
                item.detail = detail
                row["meta"].configure(text=detail)

        self.after(0, apply)

    def _set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        for button in (self.convert_btn, self.audio_btn, self.summary_btn, self.clear_btn):
            button.configure(state=state)
        self.stop_btn.configure(state="normal" if busy else "disabled", text_color=INK if busy else MUTED, fg_color=DANGER if busy else LINE)
        for row in self.rows.values():
            row["remove"].configure(state=state)

    def show_summary(self, current: Path, reports: list[Path]) -> None:
        window = ctk.CTkToplevel(self)
        window.title("视频总结")
        window.geometry("760x720")
        window.configure(fg_color=BG)
        window.transient(self)
        window.grid_columnconfigure(0, weight=1)
        window.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(window, text=current.parent.name, font=self.font_button, text_color=INK, anchor="w").grid(
            row=0, column=0, sticky="ew", padx=18, pady=(16, 4)
        )
        note = f"本批共 {len(reports)} 份，这里是最后一份。" if len(reports) > 1 else "总结已经写到输出目录。"
        ctk.CTkLabel(window, text=note, font=self.font_small, text_color=MUTED, anchor="w").grid(row=1, column=0, sticky="ew", padx=18)

        body = ctk.CTkScrollableFrame(window, fg_color="transparent")
        body.grid(row=2, column=0, sticky="nsew", padx=12, pady=8)
        body.grid_columnconfigure(0, weight=1)
        sheet = current.parent / "storyboard.jpg"
        if sheet.is_file():
            try:
                image = Image.open(sheet).convert("RGB")
                ratio = image.height / max(image.width, 1)
                width = 680
                height = max(1, int(width * ratio))
                if height > 420:
                    height = 420
                    width = max(1, int(height / max(ratio, 0.01)))
                photo = ctk.CTkImage(light_image=image, dark_image=image, size=(width, height))
                picture = ctk.CTkLabel(body, text="", image=photo)
                picture.grid(row=0, column=0, pady=(0, 8))
                window._photo = photo  # 防止图片被回收
            except OSError:
                pass
        text = ctk.CTkTextbox(body, height=280, fg_color=PANEL_2, text_color=INK, font=self.font_small, wrap="word")
        text.grid(row=1, column=0, sticky="ew")
        try:
            text.insert("end", current.read_text(encoding="utf-8"))
        except OSError as exc:
            text.insert("end", str(exc))

        actions = ctk.CTkFrame(window, fg_color="transparent")
        actions.grid(row=3, column=0, sticky="e", padx=16, pady=(0, 16))
        ctk.CTkButton(
            actions, text="打开总结", width=100, fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=ACCENT_TEXT, command=lambda: os.startfile(current)
        ).grid(row=0, column=0, padx=4)
        ctk.CTkButton(
            actions,
            text="打开目录",
            width=100,
            fg_color=PANEL_2,
            hover_color=LINE,
            text_color=INK,
            command=lambda: os.startfile(current.parent),
        ).grid(row=0, column=1, padx=4)
        window.bind("<Escape>", lambda _event: window.destroy())
        window.after(80, window.lift)

    def log(self, message: str) -> None:
        append_log(message)

        def apply() -> None:
            if not self.winfo_exists():
                return
            self.logbox.insert("end", message + "\n")
            self.logbox.see("end")

        try:
            self.after(0, apply)
        except tk.TclError:
            return

    def _save_settings(self) -> None:
        audio = self.audio_var.get()
        if audio not in AUDIO_FORMATS:
            audio = "MP3"
        try:
            save_settings(
                {
                    "output_dir": self.output_var.get().strip() or str(default_output()),
                    "preset": self.preset_var.get(),
                    "container": self.container_var.get(),
                    "audio_format": audio,
                }
            )
        except OSError as exc:
            self.log(f"设置没有保存：{exc}")

    def _on_close(self) -> None:
        self._save_settings()
        if self.busy:
            self.cancel_event.set()
        self.destroy()

    def _on_open_key(self, event):
        if event.state & 0x0001:
            self.pick_folder()
        else:
            self.pick_files()
        return "break"

    def _on_paste_key(self, event):
        widget = self.focus_get()
        if widget is not None and widget.winfo_class() in {"Entry", "Text"}:
            return None
        self.paste_paths()
        return "break"


def run_app(paths: list[str] | None = None) -> None:
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")
    app = App([Path(path) for path in (paths or [])])
    app.mainloop()
