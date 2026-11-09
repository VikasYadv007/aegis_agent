"""Aegis 2: a preview-first Windows file organization workspace."""

import csv
import logging
import os
from pathlib import Path
import queue
import threading
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import customtkinter as ctk
from aegis_analysis import analyze, AnalysisCancelled
from aegis_core import (
    data_dir,
    load_json,
    save_json,
    validate_folder,
    execute_plan,
    undo,
    recovery_sessions,
    JOURNAL,
)

APP_VERSION = "2.0.0"
BG = ("#F3F5F9", "#111827")
CARD = ("#FFFFFF", "#1B2536")
TEXT = ("#182538", "#ECF1F9")
MUTED = ("#66758B", "#A3B1C5")
BORDER = ("#E1E7EF", "#334156")
BLUE, HOVER = "#3265E8", "#2452C8"
SOFT = ("#EAF0FF", "#263B60")


def human_size(value):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:,.0f} {unit}" if unit == "B" else f"{value:,.1f} {unit}"
        value /= 1024


class AegisAgentApp(ctk.CTk):
    PAGE_SIZE = 250

    def __init__(self):
        self.settings_path = data_dir() / "aegis_config.json"
        self.history_path = data_dir() / "aegis_history.json"
        self.settings = load_json(self.settings_path, {})
        self.settings.pop("api_key", None)
        ctk.set_appearance_mode(self.settings.get("theme", "Light"))
        super().__init__()
        self.title("Aegis · File Organizer")
        # CTk geometry is in logical pixels; screen dimensions are physical on Windows.
        scale = self._get_window_scaling()
        width = min(1380, int((self.winfo_screenwidth() - 70) / scale))
        height = min(900, int((self.winfo_screenheight() - 100) / scale))
        self.geometry(f"{width}x{height}")
        self.minsize(1000, 600)
        self.configure(fg_color=BG)
        icon = Path(__file__).parent / "assets" / "aegis.ico"
        if icon.exists():
            self.after(200, lambda: self.iconbitmap(str(icon)))
        self.fonts = {
            name: ctk.CTkFont(family="Segoe UI", size=size, weight=weight)
            for name, size, weight in [
                ("title", 28, "bold"),
                ("h2", 18, "bold"),
                ("body", 13, "normal"),
                ("bold", 13, "bold"),
                ("small", 11, "normal"),
                ("metric", 26, "bold"),
            ]
        }
        saved = self.settings.get("last_dir", "")
        self.target_dir = Path(saved) if saved and Path(saved).is_dir() else None
        self.organization_plan, self.warnings = [], []
        self.busy, self.phase = False, "empty"
        self.cancel_event = threading.Event()
        self.events = queue.Queue()
        self.progress_lock = threading.Lock()
        self.pending_progress = None
        self.page, self.sort_key, self.sort_reverse = 0, "name", False
        self.render_after = None
        self.visible_indices, self.control_widgets = [], []
        self.views = {}
        self.protocol("WM_DELETE_WINDOW", self.close_app)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.create_sidebar()
        self.body = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self.body.grid(row=0, column=1, sticky="nsew", padx=26, pady=(20, 16))
        self.body.grid_columnconfigure(0, weight=1)
        self.body.grid_rowconfigure(0, weight=1)
        self.create_workspace()
        self.create_history()
        self.create_settings()
        self.create_statusbar()
        self.setup_table_style()
        self.last_theme = ctk.get_appearance_mode()
        self.switch_view("Workspace")
        self.update_folder_label()
        self.render_plan()
        self.bind("<Control-o>", lambda e: self.change_target_folder())
        self.bind("<Control-f>", self.focus_search)
        self.bind("<Control-Return>", lambda e: self.run_execution())
        self.bind("<Escape>", lambda e: self.cancel_operation() if self.busy else None)
        self.after(50, self.drain_events)

    def label(self, parent, text, font="body", color=None, **kwargs):
        return ctk.CTkLabel(
            parent, text=text, font=self.fonts[font], text_color=color or TEXT, **kwargs
        )

    def button(self, parent, text, command, primary=False, **kwargs):
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            height=34,
            corner_radius=8,
            font=self.fonts["bold"],
            fg_color=BLUE if primary else SOFT,
            hover_color=HOVER if primary else ("#DBE5FD", "#344D75"),
            text_color="#FFFFFF" if primary else (BLUE, "#B9CDFF"),
            **kwargs,
        )

    def card(self, parent, **kwargs):
        return ctk.CTkFrame(
            parent,
            fg_color=CARD,
            border_color=BORDER,
            border_width=1,
            corner_radius=12,
            **kwargs,
        )

    def page_header(self, parent, eyebrow, title, subtitle):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.label(frame, eyebrow, "small", BLUE).pack(anchor="w")
        self.label(frame, title, "title").pack(anchor="w", pady=(3, 2))
        self.label(frame, subtitle, color=MUTED).pack(anchor="w")
        return frame

    def create_sidebar(self):
        rail = ctk.CTkFrame(self, width=180, corner_radius=0, fg_color="#121F35")
        rail.grid(row=0, column=0, rowspan=2, sticky="nsew")
        rail.grid_propagate(False)
        rail.grid_columnconfigure(0, weight=1)
        rail.grid_rowconfigure(5, weight=1)
        logo = ctk.CTkFrame(rail, fg_color="transparent")
        logo.grid(row=0, column=0, padx=20, pady=(30, 35), sticky="w")
        self.label(
            logo,
            "A",
            "title",
            "#FFFFFF",
            fg_color=BLUE,
            corner_radius=12,
            width=44,
            height=44,
        ).pack(side="left")
        self.label(logo, " aegis", "h2", "#FFFFFF").pack(side="left", padx=5)
        self.label(rail, "FILE ORGANIZER", "small", "#8194B4").grid(
            row=1, column=0, sticky="w", padx=22, pady=(0, 12)
        )
        self.nav = {}
        for row, (name, caption) in enumerate(
            [
                ("Workspace", "01   Workspace"),
                ("History", "02   Recovery"),
                ("Settings", "03   Preferences"),
            ],
            2,
        ):
            button = ctk.CTkButton(
                rail,
                text=caption,
                anchor="w",
                height=44,
                corner_radius=8,
                fg_color="transparent",
                hover_color="#233752",
                text_color="#AFC0DA",
                font=self.fonts["bold"],
                command=lambda name=name: self.switch_view(name),
            )
            button.grid(row=row, column=0, padx=12, pady=4, sticky="ew")
            self.nav[name] = button
        foot = ctk.CTkFrame(rail, fg_color="#1C2D47", corner_radius=10)
        foot.grid(row=6, column=0, padx=13, pady=18, sticky="ew")
        self.label(foot, "You stay in control.", "bold", "#EAF0FF").pack(
            anchor="w", padx=12, pady=(13, 5)
        )
        self.label(
            foot,
            "Preview every move.\nKeep an undo trail.",
            "small",
            "#A8B9D2",
            justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 13))
        self.label(rail, f"AEGIS  /  {APP_VERSION}", "small", "#7186A6").grid(
            row=7, column=0, padx=22, pady=(0, 20), sticky="w"
        )

    def create_workspace(self):
        view = ctk.CTkFrame(self.body, fg_color="transparent")
        self.views["Workspace"] = view
        view.grid_columnconfigure(0, weight=1)
        view.grid_rowconfigure(4, weight=1)
        self.page_header(
            view,
            "YOUR FILES, IN ORDER",
            "A calmer workspace.",
            "Choose a folder. Review the plan. Make room for what matters.",
        ).grid(row=0, column=0, sticky="ew", pady=(0, 16))
        folder = self.card(view)
        folder.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        folder.grid_columnconfigure(0, weight=1)
        self.label(folder, "WORKING FOLDER", "small", MUTED).grid(
            row=0, column=0, padx=18, pady=(10, 0), sticky="w"
        )
        self.folder_label = self.label(folder, "", "bold", anchor="w")
        self.folder_label.grid(row=1, column=0, padx=18, pady=(0, 10), sticky="ew")
        self.folder_button = self.button(
            folder, "Choose folder", self.change_target_folder, width=124
        )
        self.folder_button.grid(row=0, column=1, rowspan=2, padx=(8, 12), pady=14)
        self.recent_menu = ctk.CTkOptionMenu(
            folder,
            values=["Recent folders"],
            width=135,
            fg_color=SOFT,
            button_color=SOFT,
            button_hover_color=("#DBE5FD", "#344D75"),
            text_color=TEXT,
            font=self.fonts["body"],
            command=self.choose_recent,
        )
        self.recent_menu.grid(row=0, column=2, rowspan=2, padx=(0, 16), pady=14)
        self.control_widgets.extend([self.folder_button, self.recent_menu])
        self.refresh_recent()
        mode = ctk.CTkFrame(view, fg_color="transparent")
        mode.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        self.label(mode, "Organize by", "bold").pack(side="left", padx=(0, 12))
        self.strategy = ctk.CTkOptionMenu(
            mode,
            values=["Smart sessions", "File type", "By month", "Gemini assisted"],
            width=172,
            fg_color=CARD,
            button_color=BLUE,
            button_hover_color=HOVER,
            text_color=TEXT,
            font=self.fonts["body"],
            command=self.strategy_changed,
        )
        self.strategy.set(self.settings.get("strategy", "Smart sessions"))
        self.strategy.pack(side="left")
        self.mode_hint = self.label(mode, "", "small", MUTED)
        self.mode_hint.pack(side="left", padx=12)
        self.analyze_button = self.button(
            mode, "Analyze folder", self.run_analysis, primary=True, width=145
        )
        self.analyze_button.pack(side="right")
        self.control_widgets.extend([self.strategy, self.analyze_button])
        self.metrics = []
        metrics = ctk.CTkFrame(view, fg_color="transparent")
        metrics.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        for index, (name, note) in enumerate(
            [
                ("FILES IN PREVIEW", "Top-level files only"),
                ("READY TO MOVE", "Included in this run"),
                ("NEEDS ATTENTION", "Suggestions or conflicts"),
                ("DUPLICATES", "Kept for your review"),
            ]
        ):
            metrics.grid_columnconfigure(index, weight=1, uniform="metric")
            card = self.card(metrics)
            card.grid(
                row=0,
                column=index,
                sticky="ew",
                padx=(0 if index == 0 else 5, 0 if index == 3 else 5),
            )
            self.label(card, name, "small", MUTED).pack(
                anchor="w", padx=14, pady=(10, 0)
            )
            number = self.label(card, "—", "metric", BLUE if index == 1 else TEXT)
            number.pack(anchor="w", padx=14)
            self.label(card, note, "small", MUTED).pack(
                anchor="w", padx=14, pady=(0, 9)
            )
            self.metrics.append(number)
        panel = self.card(view)
        panel.grid(row=4, column=0, sticky="nsew")
        panel.grid_rowconfigure(2, weight=1)
        panel.grid_columnconfigure(0, weight=1)
        toolbar = ctk.CTkFrame(panel, fg_color="transparent")
        toolbar.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 8))
        self.label(toolbar, "Organization preview", "h2").pack(side="left")
        self.search_var = tk.StringVar()
        self.search = ctk.CTkEntry(
            toolbar,
            textvariable=self.search_var,
            placeholder_text="Search files or folders · Ctrl+F",
            width=250,
            fg_color=BG,
            border_color=BORDER,
            height=32,
        )
        self.search.pack(side="right")
        self.search_var.trace_add("write", lambda *args: self.schedule_render())
        filters = ctk.CTkFrame(panel, fg_color="transparent")
        filters.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 8))
        self.filter = ctk.CTkSegmentedButton(
            filters,
            values=["All files", "Attention", "Duplicates", "Excluded"],
            command=lambda v: self.reset_page(),
            font=self.fonts["small"],
            text_color=TEXT,
            selected_color=SOFT,
            selected_hover_color=SOFT,
            unselected_color=CARD,
            unselected_hover_color=SOFT,
        )
        self.filter.set("All files")
        self.filter.pack(side="left")
        self.export_button = self.button(
            filters, "Export CSV", self.export_plan, width=94
        )
        self.export_button.pack(side="right")
        center = ctk.CTkFrame(panel, fg_color="transparent")
        center.grid(row=2, column=0, sticky="nsew", padx=12)
        center.grid_columnconfigure(0, weight=1)
        center.grid_rowconfigure(0, weight=1)
        table_frame = ctk.CTkFrame(center, fg_color=CARD, corner_radius=0)
        table_frame.grid(row=0, column=0, sticky="nsew")
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(
            table_frame,
            columns=("include", "name", "destination", "size", "status"),
            show="headings",
            selectmode="extended",
            style="Aegis.Treeview",
        )
        for key, title, width in [
            ("include", "Use", 40),
            ("name", "File name", 180),
            ("destination", "Destination folder", 190),
            ("size", "Size", 70),
            ("status", "Review", 104),
        ]:
            self.tree.heading(
                key, text=title, command=lambda key=key: self.sort_by(key)
            )
            self.tree.column(
                key,
                width=width,
                minwidth=width if key in {"include", "size"} else 90,
                stretch=key in {"name", "destination"},
            )
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)
        horizontal = ttk.Scrollbar(
            table_frame, orient="horizontal", command=self.tree.xview
        )
        horizontal.grid(row=1, column=0, sticky="ew")
        self.tree.configure(xscrollcommand=horizontal.set)
        self.tree.bind("<<TreeviewSelect>>", self.inspect_selection)
        self.tree.bind("<Button-1>", self.on_table_click)
        self.tree.bind("<space>", lambda e: self.toggle_selected())
        self.empty = ctk.CTkFrame(table_frame, fg_color=CARD, corner_radius=0)
        self.empty_title = self.label(self.empty, "A fresh start for your files.", "h2")
        self.empty_title.pack(pady=(22, 8))
        self.empty_text = self.label(self.empty, "", color=MUTED, justify="center")
        self.empty_text.pack(padx=15, pady=(0, 15))
        self.empty_action = self.button(
            self.empty, "Choose a folder", self.change_target_folder, primary=True
        )
        self.empty_action.pack(pady=(0, 20))
        inspector = ctk.CTkScrollableFrame(
            center, width=220, fg_color=BG, corner_radius=8
        )
        inspector.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        self.label(inspector, "FILE DETAILS", "small", MUTED).pack(
            anchor="w", padx=10, pady=(12, 10)
        )
        self.detail_name = self.label(
            inspector, "Select a file", "bold", wraplength=190, justify="left"
        )
        self.detail_name.pack(anchor="w", padx=10, pady=(0, 7))
        self.detail_meta = self.label(
            inspector, "", "small", MUTED, justify="left", wraplength=190
        )
        self.detail_reason = self.label(
            inspector, "", color=MUTED, wraplength=190, justify="left"
        )
        self.label(inspector, "Destination folder", "small", MUTED).pack(
            anchor="w", padx=10
        )
        self.dest_entry = ctk.CTkEntry(
            inspector, height=32, width=190, fg_color=CARD, border_color=BORDER
        )
        self.dest_entry.pack(fill="x", padx=8, pady=(5, 8))
        for name, text, command in [
            ("apply_button", "Apply to selection", self.update_file_destination),
            ("toggle_button", "Include / exclude", self.toggle_selected),
            ("reveal_button", "Show folder in Explorer", self.reveal_selection),
        ]:
            button = self.button(inspector, text, command, width=190)
            button.pack(fill="x", padx=8, pady=(0, 8))
            setattr(self, name, button)
        self.detail_meta.pack(anchor="w", padx=10, pady=(8, 10))
        self.detail_reason.pack(anchor="w", padx=10, pady=(0, 12))
        self.control_widgets.extend(
            [self.apply_button, self.toggle_button, self.dest_entry]
        )
        bottom = ctk.CTkFrame(panel, fg_color="transparent")
        bottom.grid(row=3, column=0, sticky="ew", padx=16, pady=8)
        for text, value in [("Include page", True), ("Exclude page", False)]:
            button = self.button(
                bottom, text, lambda value=value: self.set_visible(value), width=100
            )
            button.pack(side="left", padx=(0, 6))
            self.control_widgets.append(button)
        self.next_button = self.button(
            bottom, "Next", lambda: self.change_page(1), width=54
        )
        self.next_button.pack(side="right")
        self.page_label = self.label(bottom, "0 files", "small", MUTED)
        self.page_label.pack(side="right", padx=10)
        self.prev_button = self.button(
            bottom, "Previous", lambda: self.change_page(-1), width=72
        )
        self.prev_button.pack(side="right")
        actions = ctk.CTkFrame(view, fg_color="transparent")
        actions.grid(row=5, column=0, sticky="ew", pady=(12, 0))
        self.selection_summary = self.label(actions, "", color=MUTED)
        self.selection_summary.pack(side="left")
        self.execute_button = self.button(
            actions, "Organize files", self.run_execution, primary=True, width=164
        )
        self.execute_button.pack(side="right")
        self.undo_button = self.button(actions, "Undo latest", self.run_undo, width=102)
        self.undo_button.pack(side="right", padx=8)
        self.control_widgets.extend([self.execute_button, self.undo_button])
        self.strategy_changed(self.strategy.get(), persist=False)

    def create_history(self):
        view = ctk.CTkFrame(self.body, fg_color="transparent")
        self.views["History"] = view
        self.page_header(
            view,
            "A WAY BACK",
            "Recovery & activity",
            "Restore a previous session in the current folder. Conflicting files stay untouched.",
        ).pack(fill="x", pady=(0, 22))
        target = self.card(view)
        target.pack(fill="x", pady=(0, 16))
        self.recovery_target = self.label(target, "", color=MUTED, anchor="w")
        self.recovery_target.pack(fill="x", padx=18, pady=16)
        self.recovery_list = ctk.CTkScrollableFrame(view, fg_color="transparent")
        self.recovery_list.pack(fill="both", expand=True)
        self.button(
            view, "Refresh recovery sessions", self.refresh_history, width=210
        ).pack(anchor="w", pady=12)

    def create_settings(self):
        view = ctk.CTkScrollableFrame(self.body, fg_color="transparent")
        self.views["Settings"] = view
        self.page_header(
            view,
            "MAKE IT YOURS",
            "Preferences",
            "A few thoughtful defaults. You decide how your workspace works.",
        ).pack(fill="x", pady=(0, 22))
        appearance = self.card(view)
        appearance.pack(fill="x", pady=(0, 14))
        self.label(appearance, "Appearance", "h2").pack(
            anchor="w", padx=22, pady=(18, 5)
        )
        self.label(
            appearance,
            "Choose a light, dark, or system-matched workspace.",
            color=MUTED,
        ).pack(anchor="w", padx=22)
        self.theme_menu = ctk.CTkSegmentedButton(
            appearance,
            values=["Light", "Dark", "System"],
            command=self.change_theme,
            selected_color=SOFT,
            selected_hover_color=SOFT,
            unselected_color=CARD,
            unselected_hover_color=SOFT,
            text_color=TEXT,
            font=self.fonts["body"],
        )
        self.theme_menu.set(self.settings.get("theme", "Light"))
        self.theme_menu.pack(anchor="w", padx=22, pady=18)
        rules = self.card(view)
        rules.pack(fill="x", pady=(0, 14))
        self.label(rules, "Analysis rules", "h2").pack(
            anchor="w", padx=22, pady=(18, 5)
        )
        self.duplicate_var = tk.BooleanVar(value=self.settings.get("duplicates", True))
        ctk.CTkSwitch(
            rules,
            text="Find exact duplicates and put them in a review folder",
            variable=self.duplicate_var,
            progress_color=BLUE,
            command=self.save_preferences,
            font=self.fonts["body"],
            text_color=TEXT,
        ).pack(anchor="w", padx=22, pady=14)
        self.label(
            rules, "Ignore filenames or extensions, separated by commas", color=MUTED
        ).pack(anchor="w", padx=22, pady=(5, 7))
        self.exclusions = ctk.CTkEntry(
            rules, height=38, fg_color=BG, border_color=BORDER
        )
        self.exclusions.insert(
            0, self.settings.get("exclusions", ".ini, .tmp, .sys, .lnk")
        )
        self.exclusions.pack(fill="x", padx=22, pady=(0, 10))
        self.button(rules, "Save rules", self.save_preferences, width=120).pack(
            anchor="w", padx=22, pady=(0, 18)
        )
        self.label(
            rules,
            "Rules apply on the next analysis. Downloads in progress and app state files are always excluded.",
            "small",
            MUTED,
        ).pack(anchor="w", padx=22, pady=(0, 18))
        ai = self.card(view)
        ai.pack(fill="x", pady=(0, 14))
        self.label(ai, "Optional Gemini naming", "h2").pack(
            anchor="w", padx=22, pady=(18, 5)
        )
        self.label(
            ai,
            "Only filenames and website origins are sent, after confirmation. Offline modes need no API key.",
            color=MUTED,
        ).pack(anchor="w", padx=22)
        self.api_entry = ctk.CTkEntry(
            ai,
            placeholder_text="API key · kept only for this session",
            show="*",
            height=38,
            fg_color=BG,
            border_color=BORDER,
        )
        self.api_entry.pack(fill="x", padx=22, pady=14)
        self.label(
            ai,
            "Network requests time out. Unavailable AI suggestions fall back to offline naming.",
            "small",
            MUTED,
        ).pack(anchor="w", padx=22, pady=(0, 18))
        about = self.card(view)
        about.pack(fill="x", pady=(0, 14))
        self.label(about, "Built for deliberate changes", "h2").pack(
            anchor="w", padx=22, pady=(18, 8)
        )
        self.label(
            about,
            "No automatic deletion. No background moving. No recursive scanning.\nExisting files are never overwritten. Recovery records are saved before each move.",
            color=MUTED,
            justify="left",
        ).pack(anchor="w", padx=22, pady=(0, 15))
        self.button(
            about,
            "Open settings & logs",
            lambda: os.startfile(str(data_dir())),
            width=190,
        ).pack(anchor="w", padx=22, pady=(0, 18))

    def create_statusbar(self):
        bar = ctk.CTkFrame(self, fg_color=CARD, corner_radius=0, height=42)
        bar.grid(row=1, column=1, sticky="ew")
        bar.grid_columnconfigure(0, weight=1)
        self.status_label = self.label(
            bar, "Ready · Choose a folder to start", "small", MUTED, anchor="w"
        )
        self.status_label.grid(row=0, column=0, sticky="ew", padx=26, pady=10)
        self.progress = ctk.CTkProgressBar(
            bar, width=130, height=5, progress_color=BLUE
        )
        self.progress.grid(row=0, column=1, padx=12)
        self.progress.set(0)
        self.cancel_button = self.button(bar, "Cancel", self.cancel_operation, width=70)
        self.cancel_button.grid(row=0, column=2, padx=(0, 18), pady=5)
        self.cancel_button.configure(state="disabled")

    def setup_table_style(self):
        dark = ctk.get_appearance_mode() == "Dark"
        bg, fg, border = (
            ("#1B2536", "#E4ECF8", "#334156")
            if dark
            else ("#FFFFFF", "#25344B", "#E1E7EF")
        )
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "Aegis.Treeview",
            background=bg,
            fieldbackground=bg,
            foreground=fg,
            rowheight=36,
            borderwidth=0,
            font=("Segoe UI", 10),
        )
        style.configure(
            "Aegis.Treeview.Heading",
            background="#253247" if dark else "#F1F4F9",
            foreground="#B6C6DB" if dark else "#60718A",
            font=("Segoe UI", 9, "bold"),
            padding=(8, 10),
            borderwidth=0,
            relief="flat",
        )
        style.map(
            "Aegis.Treeview",
            background=[("selected", "#2C4B7A" if dark else "#E7EFFF")],
            foreground=[("selected", "#FFFFFF" if dark else "#1949B6")],
        )
        style.map("Aegis.Treeview.Heading", background=[("active", border)])
        for tag, color in [
            ("attention", "#F1C26C" if dark else "#98620C"),
            ("excluded", "#8A9AAF" if dark else "#8994A3"),
            ("moved", "#65D4B2" if dark else "#14735C"),
        ]:
            self.tree.tag_configure(tag, foreground=color)
        self.tree.tag_configure(
            "alternate", background="#202C3F" if dark else "#F9FBFE"
        )

    def switch_view(self, name):
        self.current_view = name
        for key, view in self.views.items():
            view.grid_remove()
            self.nav[key].configure(
                fg_color="#2A4370" if key == name else "transparent",
                text_color="#FFFFFF" if key == name else "#AFC0DA",
            )
        self.views[name].grid(row=0, column=0, sticky="nsew")
        if name == "History":
            self.refresh_history()

    def notify(self, text):
        self.status_label.configure(text=text)

    def focus_search(self, event=None):
        self.switch_view("Workspace")
        self.search.focus_set()
        return "break"

    def persist(self):
        save_json(self.settings_path, self.settings)

    def change_theme(self, value):
        ctk.set_appearance_mode(value)
        self.settings["theme"] = value
        self.persist()
        self.setup_table_style()

    def save_preferences(self):
        self.settings["duplicates"] = self.duplicate_var.get()
        if hasattr(self, "exclusions"):
            self.settings["exclusions"] = self.exclusions.get().strip()
        self.persist()
        self.notify("Preferences saved · They apply to your next analysis")

    def strategy_changed(self, value, persist=True):
        hints = {
            "Smart sessions": "Website origins, names & time",
            "File type": "Documents, images, archives & more",
            "By month": "Use each file’s last modified month",
            "Gemini assisted": "Optional AI · API key in Preferences",
        }
        self.mode_hint.configure(text=hints.get(value, ""))
        self.settings["strategy"] = value
        if persist:
            self.persist()
            self.notify("Mode changed · Analyze again to create a new preview")

    def refresh_recent(self):
        self.recent_paths = [
            p for p in self.settings.get("recent_folders", []) if Path(p).is_dir()
        ][:7]
        self.recent_menu.configure(
            values=["Recent folders"]
            + [f"{i+1}. {Path(p).name}" for i, p in enumerate(self.recent_paths)]
        )
        self.recent_menu.set("Recent folders")

    def choose_recent(self, choice):
        if not self.busy and choice != "Recent folders":
            self.set_target(Path(self.recent_paths[int(choice.split(".")[0]) - 1]))
        self.recent_menu.set("Recent folders")

    def change_target_folder(self):
        if self.busy:
            return
        selected = filedialog.askdirectory(
            title="Choose a folder to organize",
            initialdir=self.target_dir or Path.home(),
        )
        if selected:
            self.set_target(Path(selected))

    def set_target(self, path):
        if self.busy:
            return
        path = Path(path).resolve()
        if not path.is_dir():
            messagebox.showerror("Folder unavailable", "Choose an existing folder.")
            return
        if (
            self.organization_plan
            and self.phase == "preview"
            and not messagebox.askyesno(
                "Replace preview?",
                "Changing folders clears this preview. No files will be moved. Continue?",
            )
        ):
            return
        self.target_dir = path
        self.settings["last_dir"] = str(path)
        self.settings["recent_folders"] = [str(path)] + [
            p for p in self.settings.get("recent_folders", []) if p != str(path)
        ][:6]
        self.persist()
        self.organization_plan = []
        self.phase = "empty"
        self.search_var.set("")
        self.filter.set("All files")
        self.refresh_recent()
        self.update_folder_label()
        self.render_plan()
        self.notify("Folder selected · Analyze to see a preview")

    def update_folder_label(self):
        text = str(self.target_dir) if self.target_dir else "Choose a folder to begin"
        self.folder_label.configure(text=text if len(text) < 80 else "…" + text[-77:])
        self.folder_button.configure(
            text="Change folder" if self.target_dir else "Choose folder"
        )

    def post(self, callback):
        self.events.put(callback)

    def report_progress(self, done, total, message):
        with self.progress_lock:
            self.pending_progress = (done, total, message)

    def drain_events(self):
        for _ in range(40):
            try:
                callback = self.events.get_nowait()
            except queue.Empty:
                break
            try:
                callback()
            except Exception as exc:
                logging.exception("UI update failed")
                self.notify(f"Could not update the view: {exc}")
        with self.progress_lock:
            value, self.pending_progress = self.pending_progress, None
        if value and self.busy:
            done, total, message = value
            self.notify(message[:120])
            self.progress.set(done / total if total else 0)
        if ctk.get_appearance_mode() != self.last_theme:
            self.last_theme = ctk.get_appearance_mode()
            self.setup_table_style()
        self.after(50, self.drain_events)

    def start_worker(self, work, complete, label):
        if self.busy:
            return
        self.busy = True
        self.cancel_event.clear()
        self.notify(label)
        self.cancel_button.configure(state="normal", text="Cancel")
        for widget in self.control_widgets:
            widget.configure(state="disabled")
        self.update_actions()

        def run():
            try:
                result = work()
                self.post(lambda: self.finish_worker(complete, result))
            except AnalysisCancelled:
                self.post(
                    lambda: self.finish_worker(
                        lambda result: self.notify(
                            "Analysis cancelled · No files were moved"
                        ),
                        None,
                    )
                )
            except Exception as exc:
                logging.exception("Operation failed")
                self.post(
                    lambda text=str(exc): self.finish_worker(self.show_error, text)
                )

        threading.Thread(target=run, daemon=False, name="Aegis worker").start()

    def finish_worker(self, complete, result):
        self.busy = False
        with self.progress_lock:
            self.pending_progress = None
        for widget in self.control_widgets:
            widget.configure(state="normal")
        self.cancel_button.configure(state="disabled", text="Cancel")
        self.progress.set(0)
        complete(result)
        self.update_actions()
        if self.current_view == "History":
            self.refresh_history()

    def show_error(self, text):
        self.notify("Operation stopped · Review the error before continuing")
        self.render_plan()
        messagebox.showerror(
            "Aegis could not finish",
            text + "\n\nExisting recovery records remain available in Recovery.",
        )

    def cancel_operation(self):
        if self.busy:
            self.cancel_event.set()
            self.cancel_button.configure(state="disabled", text="Stopping")
            self.notify("Stopping safely after the current file or network request…")

    def close_app(self):
        if self.busy:
            self.cancel_operation()
            messagebox.showinfo(
                "Stopping safely",
                "Cancellation requested. Wait for the operation to stop, then close the window.",
            )
            return
        self.destroy()

    def run_analysis(self):
        if self.busy:
            return
        if not self.target_dir:
            self.change_target_folder()
            if not self.target_dir:
                return
        if (
            self.organization_plan
            and self.phase == "preview"
            and not messagebox.askyesno(
                "Refresh preview?",
                "A new analysis replaces current selections and destination edits. Continue?",
            )
        ):
            return
        strategy, key = self.strategy.get(), self.api_entry.get().strip()
        if strategy == "Gemini assisted":
            if not key:
                self.switch_view("Settings")
                self.api_entry.focus_set()
                self.notify(
                    "Enter a Gemini API key, or choose an offline mode in Workspace"
                )
                return
            if not messagebox.askyesno(
                "Use Gemini naming?",
                "Filenames and website origins will be sent to Google Gemini. File contents are not sent. API usage may incur charges. Continue?",
            ):
                return
        self.switch_view("Workspace")
        root = self.target_dir
        options = dict(
            strategy=strategy,
            exclusions=self.settings.get("exclusions", ".ini, .tmp, .sys, .lnk"),
            duplicates=self.settings.get("duplicates", True),
            cancel=self.cancel_event,
            progress=self.report_progress,
            api_key=key,
            model=os.environ.get("AEGIS_GEMINI_MODEL", "gemini-2.5-flash"),
        )
        self.start_worker(
            lambda: analyze(root, **options),
            self.analysis_done,
            "Analyzing folder · No files will be moved",
        )

    def analysis_done(self, result):
        self.organization_plan, self.warnings = result
        self.phase = "preview"
        self.page = 0
        self.filter.set("All files")
        self.search_var.set("")
        self.render_plan()
        self.notify(
            f"Preview ready · {len(self.organization_plan):,} files · Review before organizing"
        )
        if self.warnings:
            messagebox.showwarning(
                "Some files could not be analyzed", "\n".join(self.warnings[:15])
            )

    def schedule_render(self):
        if self.render_after:
            self.after_cancel(self.render_after)
        self.render_after = self.after(180, self.reset_page)

    def reset_page(self):
        self.render_after = None
        self.page = 0
        self.render_plan()

    def sort_by(self, key):
        self.sort_reverse = not self.sort_reverse if key == self.sort_key else False
        self.sort_key = key
        self.render_plan()

    def change_page(self, delta):
        self.page = max(0, self.page + delta)
        self.render_plan()

    def display_status(self, item):
        if item["status"] != "Will Move":
            return item["status"]
        if not item.get("included", True):
            return "Excluded"
        if item["duplicate"]:
            return "Duplicate"
        return "Review name" if item["confidence"] < 70 else "Ready"

    def render_plan(self):
        if not hasattr(self, "tree"):
            return
        selected = set(self.tree.selection())
        self.tree.delete(*self.tree.get_children())
        term, choice = self.search_var.get().casefold().strip(), self.filter.get()

        def match(item):
            if (
                term
                and term
                not in (item["record"].name + " " + item["dest_folder"]).casefold()
            ):
                return False
            if choice == "Attention":
                return item["confidence"] < 70 or item["status"] in {
                    "Conflict",
                    "Skipped",
                }
            if choice == "Duplicates":
                return item["duplicate"]
            if choice == "Excluded":
                return not item.get("included", True)
            return True

        indices = [i for i, item in enumerate(self.organization_plan) if match(item)]

        def key(index):
            item = self.organization_plan[index]
            return {
                "name": item["record"].name.casefold(),
                "destination": item["dest_folder"].casefold(),
                "size": item["record"].size,
                "status": self.display_status(item),
                "include": item.get("included", True),
            }[self.sort_key]

        indices.sort(key=key, reverse=self.sort_reverse)
        pages = max(1, (len(indices) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        self.page = min(self.page, pages - 1)
        self.visible_indices = indices[
            self.page * self.PAGE_SIZE : (self.page + 1) * self.PAGE_SIZE
        ]
        for row, index in enumerate(self.visible_indices):
            item = self.organization_plan[index]
            status = self.display_status(item)
            tags = ["alternate"] if row % 2 else []
            if status in {"Conflict", "Skipped", "Review name"}:
                tags.append("attention")
            elif status == "Excluded":
                tags.append("excluded")
            elif status == "Moved":
                tags.append("moved")
            self.tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    "✓" if item.get("included", True) else "—",
                    item["record"].name,
                    item["dest_folder"],
                    human_size(item["record"].size),
                    status,
                ),
                tags=tags,
            )
        for iid in selected:
            if self.tree.exists(iid):
                self.tree.selection_add(iid)
        self.page_label.configure(
            text=f"{len(indices):,} files · {self.page+1} / {pages}"
        )
        self.prev_button.configure(state="normal" if self.page else "disabled")
        self.next_button.configure(
            state="normal" if self.page < pages - 1 else "disabled"
        )
        total = len(self.organization_plan)
        ready = self.ready_items()
        attention = sum(
            item["confidence"] < 70 or item["status"] in {"Conflict", "Skipped"}
            for item in self.organization_plan
        )
        duplicates = sum(item["duplicate"] for item in self.organization_plan)
        for label, value in zip(
            self.metrics, [total, len(ready), attention, duplicates]
        ):
            label.configure(text=f"{value:,}" if total else "—")
        if not indices:
            self.empty.place(relx=0, rely=0.13, relwidth=0.98, relheight=0.84)
            if total:
                title, body = (
                    "No matching files.",
                    "Try a different search or filter. Your preview is still here.",
                )
                self.empty_action.configure(
                    text="Clear filters", command=self.clear_filters
                )
            elif self.phase == "empty":
                title, body = (
                    "A fresh start for your files.",
                    "Analyze a folder to see where every file will go.\nNothing moves until you approve the preview.",
                )
                self.empty_action.configure(
                    text="Analyze folder" if self.target_dir else "Choose a folder",
                    command=(
                        self.run_analysis
                        if self.target_dir
                        else self.change_target_folder
                    ),
                )
            else:
                title, body = (
                    "All clear.",
                    "No eligible loose files were found.\nSubfolders and excluded files are left untouched.",
                )
                self.empty_action.configure(
                    text="Choose another folder", command=self.change_target_folder
                )
            self.empty_title.configure(text=title)
            self.empty_text.configure(text=body)
        else:
            self.empty.place_forget()
        self.inspect_selection()
        self.update_actions()

    def clear_filters(self):
        self.search_var.set("")
        self.filter.set("All files")
        self.reset_page()

    def ready_items(self):
        return [
            item
            for item in self.organization_plan
            if item.get("included", True) and item["status"] == "Will Move"
        ]

    def update_actions(self):
        if not hasattr(self, "execute_button"):
            return
        ready = self.ready_items()
        can_move = bool(ready) and self.phase == "preview" and not self.busy
        self.execute_button.configure(
            state="normal" if can_move else "disabled",
            text=f"Organize {len(ready):,} files" if ready else "Organize files",
        )
        if self.phase == "result":
            count = sum(item["status"] == "Moved" for item in self.organization_plan)
            self.selection_summary.configure(
                text=f"{count:,} moved · Analyze again for a new plan."
            )
        else:
            self.selection_summary.configure(
                text=f'{len(ready):,} selected · {human_size(sum(item["record"].size for item in ready))} · No files are deleted'
            )
        recoverable = bool(self.target_dir and (self.target_dir / JOURNAL).exists())
        self.undo_button.configure(
            state="normal" if recoverable and not self.busy else "disabled"
        )
        self.export_button.configure(
            state="normal" if self.organization_plan and not self.busy else "disabled"
        )
        self.empty_action.configure(state="disabled" if self.busy else "normal")

    def selected_indices(self):
        return [int(iid) for iid in self.tree.selection()]

    def inspect_selection(self, event=None):
        indices = self.selected_indices()
        if not indices:
            self.detail_name.configure(text="Select a file")
            self.detail_meta.configure(
                text="Inspect its destination and\nwhy it was suggested."
            )
            self.detail_reason.configure(
                text="Tip: Ctrl-click or Shift-click\nto edit multiple files together."
            )
            self.dest_entry.delete(0, "end")
            return
        item = self.organization_plan[indices[0]]
        record = item["record"]
        self.detail_name.configure(
            text=record.name if len(indices) == 1 else f"{len(indices)} files selected"
        )
        self.detail_meta.configure(
            text=f'{human_size(record.size)} · {record.ext or "No extension"}\nModified {datetime.fromtimestamp(record.time):%d %b %Y, %H:%M}'
        )
        self.detail_reason.configure(text=item.get("error") or item["reason"])
        self.dest_entry.delete(0, "end")
        self.dest_entry.insert(0, item["dest_folder"])

    def on_table_click(self, event):
        if (
            self.tree.identify_column(event.x) == "#1"
            and self.tree.identify_region(event.x, event.y) == "cell"
        ):
            iid = self.tree.identify_row(event.y)
            if iid:
                self.tree.selection_set(iid)
                self.toggle_selected()
                return "break"

    def toggle_selected(self):
        if self.busy or self.phase != "preview":
            return "break"
        indices = self.selected_indices()
        include = not all(
            self.organization_plan[i].get("included", True) for i in indices
        )
        for index in indices:
            item = self.organization_plan[index]
            if item["status"] == "Will Move":
                item["included"] = include
        self.render_plan()
        return "break"

    def set_visible(self, include):
        if self.busy or self.phase != "preview":
            return
        for index in self.visible_indices:
            if self.organization_plan[index]["status"] == "Will Move":
                self.organization_plan[index]["included"] = include
        self.render_plan()

    def update_file_destination(self):
        if self.busy or self.phase != "preview":
            return
        indices = self.selected_indices()
        if not indices:
            self.notify("Select one or more files before editing a destination")
            return
        try:
            name = validate_folder(self.dest_entry.get().strip())
            folder = self.target_dir / name
            if folder.resolve().parent != self.target_dir.resolve():
                raise ValueError("The destination must stay inside the working folder.")
        except ValueError as exc:
            messagebox.showerror("Invalid folder name", str(exc))
            return
        for index in indices:
            item = self.organization_plan[index]
            conflict = (folder / item["record"].name).exists() or (
                folder.exists() and not folder.is_dir()
            )
            item.update(
                dest_folder=name,
                reason="Destination chosen by you",
                confidence=100,
                status="Conflict" if conflict else "Will Move",
                error="Destination already exists" if conflict else "",
                included=not conflict,
            )
        self.render_plan()
        self.notify(f"Destination updated for {len(indices)} files")

    def reveal_selection(self):
        indices = self.selected_indices()
        if not indices or not self.target_dir:
            return
        item = self.organization_plan[indices[0]]
        folder = (
            self.target_dir / item["dest_folder"]
            if item["status"] == "Moved"
            else self.target_dir
        )
        if folder.is_dir():
            os.startfile(str(folder))

    def run_execution(self):
        if self.busy or self.phase != "preview":
            return
        plan = self.ready_items()
        if not plan:
            return
        count = len({item["dest_folder"] for item in plan})
        if not messagebox.askyesno(
            "Organize these files?",
            f"Move {len(plan):,} files into {count:,} folders?\n\n{self.target_dir}\n\nExisting destinations will be skipped. You can undo this session in Recovery.",
        ):
            return
        root = self.target_dir

        def work():
            count, errors = execute_plan(
                root, plan, self.report_progress, self.cancel_event
            )
            self.record_history(
                "Organize", root, count, len(errors), self.cancel_event.is_set()
            )
            return count, errors

        self.start_worker(
            work,
            self.execution_done,
            "Organizing · Saving recovery records before each move",
        )

    def record_history(self, action, root, count, failures, cancelled):
        try:
            history = load_json(self.history_path, [])
            history.append(
                {
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "target": str(root),
                    "action": action,
                    "files_moved": count,
                    "failures": failures,
                    "cancelled": cancelled,
                }
            )
            save_json(self.history_path, history[-1000:])
        except OSError:
            logging.exception("Activity history could not be saved")

    def execution_done(self, result):
        count, errors = result
        for item in self.organization_plan:
            if item["status"] == "Will Move" and item.get("included", True):
                item["status"] = "Not moved"
        self.phase = "result"
        self.render_plan()
        prefix = (
            "Stopped safely" if self.cancel_event.is_set() else "Organization complete"
        )
        self.notify(
            f"{prefix} · {count:,} moved · {len(errors):,} skipped · Recovery is available"
        )
        if errors:
            messagebox.showwarning(
                "Some files stayed in place",
                "\n".join(errors[:12])
                + "\n\nSelect a skipped file to see its reason, or export the full CSV report.",
            )

    def run_undo(self, journal=None):
        if self.busy or not self.target_dir:
            return
        journal = Path(journal) if journal else self.target_dir / JOURNAL
        if not journal.exists():
            self.notify("No recovery session is available in this folder")
            return
        if not messagebox.askyesno(
            "Restore this session?",
            "Return files to their original locations?\n\nExisting or modified files will be left untouched. Recover newer sessions first if they involve the same files.",
        ):
            return
        root = self.target_dir

        def work():
            count, errors = undo(root, journal, self.report_progress, self.cancel_event)
            self.record_history(
                "Restore", root, count, len(errors), self.cancel_event.is_set()
            )
            return count, errors

        self.start_worker(work, self.undo_done, "Restoring original file locations")

    def undo_done(self, result):
        count, errors = result
        self.organization_plan = []
        self.phase = "empty"
        self.render_plan()
        self.refresh_history()
        prefix = "Stopped safely" if self.cancel_event.is_set() else "Recovery complete"
        self.notify(f"{prefix} · {count:,} files restored · {len(errors):,} conflicts")
        if errors:
            messagebox.showwarning(
                "Recovery needs attention",
                "\n".join(errors[:12])
                + "\n\nThe session has been kept so you can retry.",
            )

    def refresh_history(self):
        if not hasattr(self, "recovery_list"):
            return
        for widget in self.recovery_list.winfo_children():
            widget.destroy()
        self.recovery_target.configure(
            text=(
                str(self.target_dir)
                if self.target_dir
                else "Choose a working folder in Workspace first."
            )
        )
        sessions = recovery_sessions(self.target_dir) if self.target_dir else []
        self.label(self.recovery_list, "Available recovery sessions", "h2").pack(
            anchor="w", padx=4, pady=(4, 12)
        )
        if not sessions:
            self.label(
                self.recovery_list,
                "Nothing to restore yet. Completed moves will appear here.",
                color=MUTED,
            ).pack(anchor="w", padx=4, pady=12)
        for path in sessions[:100]:
            card = self.card(self.recovery_list)
            card.pack(fill="x", pady=5)
            card.grid_columnconfigure(0, weight=1)
            label = "Latest session" if path.name == JOURNAL else "Earlier session"
            stamp = datetime.fromtimestamp(path.stat().st_mtime).strftime(
                "%d %b %Y · %H:%M"
            )
            self.label(card, label, "bold").grid(
                row=0, column=0, sticky="w", padx=18, pady=(12, 0)
            )
            self.label(card, stamp, "small", MUTED).grid(
                row=1, column=0, sticky="w", padx=18, pady=(0, 12)
            )
            button = self.button(
                card,
                "Restore session",
                lambda path=path: self.run_undo(path),
                width=140,
            )
            button.grid(row=0, column=1, rowspan=2, padx=18)
            button.configure(state="disabled" if self.busy else "normal")
        self.label(self.recovery_list, "Recent activity", "h2").pack(
            anchor="w", padx=4, pady=(26, 12)
        )
        history = load_json(self.history_path, [])
        local = [
            item
            for item in history
            if self.target_dir and item.get("target") == str(self.target_dir)
        ]
        if not local:
            self.label(
                self.recovery_list,
                "Activity for this folder appears after your first run.",
                color=MUTED,
            ).pack(anchor="w", padx=4)
        for item in reversed(local[-30:]):
            suffix = " · cancelled" if item.get("cancelled") else ""
            text = f'{item.get("date", "")}    {item.get("action", "Organize")}    {item.get("files_moved",0)} files · {item.get("failures",0)} skipped{suffix}'
            self.label(self.recovery_list, text, color=MUTED).pack(
                anchor="w", padx=4, pady=4
            )

    def export_plan(self, destination=None):
        if self.busy or not self.organization_plan:
            return
        path = destination or filedialog.asksaveasfilename(
            title="Export organization report",
            defaultextension=".csv",
            initialfile="Aegis-report.csv",
            filetypes=[("CSV report", "*.csv")],
        )
        if not path:
            return

        def cell(value):
            value = str(value)
            return (
                "'" + value
                if value.startswith(("=", "+", "-", "@", "\t", "\r"))
                else value
            )

        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(
                    [
                        "File",
                        "Source",
                        "Destination folder",
                        "Bytes",
                        "Included",
                        "Status",
                        "Reason",
                    ]
                )
                for item in self.organization_plan:
                    writer.writerow(
                        [
                            cell(item["record"].name),
                            cell(item["record"].path),
                            cell(item["dest_folder"]),
                            item["record"].size,
                            item.get("included", True),
                            self.display_status(item),
                            cell(item.get("error") or item["reason"]),
                        ]
                    )
            self.notify(f"Report exported · {Path(path).name}")
        except OSError as exc:
            messagebox.showerror("Could not export report", str(exc))


if __name__ == "__main__":
    AegisAgentApp().mainloop()
