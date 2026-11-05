import os
import shutil
import json
import time
import threading
import hashlib
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse
import re
from collections import Counter

import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# ----------------------------------------------------
# 🛡 SAFE OPTIONAL DEPENDENCY IMPORTS
# ----------------------------------------------------
try:
    from PIL import Image
    import PyPDF2
    import docx
    from google import genai
except ImportError:
    pass

# ==========================================
# ⚙️ CONFIGURATION & CONSTANTS
# ==========================================
APP_VERSION = "1.3.0"
MAX_MINUTES_STRICT = 5    
MAX_MINUTES_RELAXED = 30  
UNDO_LOG_FILE = "aegis_undo_log.json"
CONFIG_FILE = "aegis_config.json"
HISTORY_FILE = "aegis_history.json"

NOISE_WORDS = {
    "screencapture", "screenshot", "snip", "dashboard", "download", "downloads",
    "image", "img", "file", "document", "copy", "new", "untitled", "preview",
    "page", "report", "final", "temp", "tmp", "edit", "result", "details", "login",
    "aspx", "html", "php", "index", "www", "com", "org", "net", "app", "io", "en", "us",
    "review", "module", "summary", "profile", "history", "compose", "mail"
}

def load_json(filepath, default_val):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f: return json.load(f)
        except: return default_val
    return default_val

def save_json(filepath, data):
    with open(filepath, "w", encoding="utf-8") as f: json.dump(data, f, indent=4)

# ==========================================
# 🧠 CORE MODELS & INTELLIGENCE
# ==========================================
def calculate_file_hash(filepath, block_size=65536):
    """Calculates SHA256 safely for duplicate detection."""
    hasher = hashlib.sha256()
    try:
        with open(filepath, 'rb') as f:
            buf = f.read(block_size)
            while len(buf) > 0:
                hasher.update(buf)
                buf = f.read(block_size)
        return hasher.hexdigest()
    except: return None

def extract_screencapture_domain(filename):
    match = re.search(r"screencapture-([a-zA-Z0-9.-]+)", filename, re.IGNORECASE)
    if match:
        raw_slug = match.group(1)
        tokens = [t for t in re.split(r"[-._]", raw_slug) if t.lower() not in {"com", "org", "net", "in", "io", "app"}]
        clean_tokens = [t for t in tokens if not (len(t) >= 8 and any(c.isupper() for c in t) and any(c.islower() for c in t) and any(c.isdigit() for c in t))]
        if clean_tokens: return clean_tokens[0].lower()
    return None

class FileRecord:
    def __init__(self, path):
        self.path = Path(path)
        self.name = self.path.name
        self.ext = self.path.suffix.lower()
        stat = self.path.stat()
        self.time = stat.st_mtime 
        self.size = stat.st_size
        self.is_screenshot = any(w in self.name.lower() for w in ["screenshot", "snip", "screencapture"])
        self.hash = None 
        
        self.domain = self._get_download_url()
        if not self.domain and self.is_screenshot:
            self.domain = extract_screencapture_domain(self.name)

    def _get_download_url(self):
        ads_path = str(self.path) + ":Zone.Identifier"
        try:
            with open(ads_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.startswith("HostUrl=") or line.startswith("ReferrerUrl="):
                        url = line.strip().split("=", 1)[1]
                        if "extension://" in url: continue
                        domain = urlparse(url).netloc.replace("www.", "")
                        if len(domain) == 32 and domain.isalpha() and domain.islower(): continue
                        return domain
        except: pass
        return None

def safe_move(src_path, dest_path):
    src_path, dest_path = Path(src_path), Path(dest_path)
    stat = src_path.stat()
    original_atime, original_mtime = stat.st_atime, stat.st_mtime
    shutil.move(str(src_path), str(dest_path))
    os.utime(str(dest_path), (original_atime, original_mtime))

# ==========================================
# 📐 ORGANIZATION LOGIC
# ==========================================
def heuristic_cluster_naming(cluster, date_str):
    detected_sources = []
    token_counter = Counter()

    for f in cluster:
        if f.domain:
            clean_dom = f.domain.split('.')[0].capitalize()
            if len(clean_dom) > 2: detected_sources.append(clean_dom)

        name = Path(f.name).stem
        name = re.sub(r'^screencapture-[a-zA-Z0-9-]+-?', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\b20[1-3][0-9][-_\s]?(0[1-9]|1[0-2])[-_\s]?(0[1-9]|[12][0-9]|3[01])\b', ' ', name)
        name = re.sub(r'\b[0-2][0-9][-_\s][0-5][0-9][-_\s][0-5][0-9]\b', ' ', name)
        name = re.sub(r'\b[a-fA-F0-9]{10,}\b', ' ', name)
        name = re.sub(r'\b[A-Za-z0-9]{15,}\b', ' ', name)

        words = re.split(r'[^A-Za-z]+', name)
        for w in words:
            if len(w) > 2 and w.lower() not in NOISE_WORDS:
                token_counter[w.capitalize()] += 1

    primary_source = Counter(detected_sources).most_common(1)[0][0] if detected_sources else None

    meaningful_tokens = []
    for word, _ in token_counter.most_common(10):
        if primary_source and word.lower() in primary_source.lower(): continue
        meaningful_tokens.append(word)
        if len(meaningful_tokens) >= 3: break
            
    topic = " ".join(meaningful_tokens) if meaningful_tokens else None

    if primary_source and topic: 
        return f"{date_str}_{primary_source} - {topic}", 90, "Heuristic Web Domain + Content Match"
    elif primary_source: 
        return f"{date_str}_{primary_source}", 80, "Web Domain Match"
    elif topic: 
        return f"{date_str}_{topic}", 60, "Common Filename Keywords"
    
    types = list({f.ext.replace('.', '').upper() for f in cluster if f.ext})
    folder_name = f"{' & '.join(types[:2])} Files" if types else "Uncategorized Session"
    return f"{date_str}_{folder_name}", 40, "Generic File Type Match"

# ==========================================
# 🖥️ MAIN APPLICATION
# ==========================================
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

class AegisAgentApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title(f"Aegis - Intelligent File Architecture v{APP_VERSION}")
        self.geometry("1280x800")
        self.minsize(1000, 700)
        
        self.config = load_json(CONFIG_FILE, {})
        self.target_dir = Path(self.config.get("last_dir", str(Path.home())))
        
        self.organization_plan = [] 
        self.current_step = 1
        
        # Typography
        self.fonts = {
            "h1": ctk.CTkFont(family="Segoe UI", size=28, weight="bold"),
            "h2": ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            "h3": ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            "body": ctk.CTkFont(family="Segoe UI", size=13),
            "body_bold": ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            "small": ctk.CTkFont(family="Segoe UI", size=12),
        }

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        self.setup_styles()
        self.create_sidebar()
        
        self.main_container = ctk.CTkFrame(self, fg_color=("#F3F3F3", "#202020"), corner_radius=0)
        self.main_container.grid(row=0, column=1, sticky="nsew")
        self.main_container.grid_rowconfigure(0, weight=1)
        self.main_container.grid_columnconfigure(0, weight=1)
        
        self.views = {}
        self.create_dashboard_view()
        self.create_organize_view()
        self.create_history_view()
        self.create_settings_view()
        
        self.switch_view("Dashboard")

    def setup_styles(self):
        self.style = ttk.Style(self)
        self.style.theme_use("default")
        bg_color = "#202020" if ctk.get_appearance_mode() == "Dark" else "#F3F3F3"
        fg_color = "#FFFFFF" if ctk.get_appearance_mode() == "Dark" else "#111111"
        sel_color = "#0078D4"
        
        self.style.configure("Treeview", background=bg_color, foreground=fg_color, 
                             fieldbackground=bg_color, borderwidth=0, font=("Segoe UI", 11), rowheight=30)
        self.style.map('Treeview', background=[('selected', sel_color)])
        self.style.configure("Treeview.Heading", background=bg_color, foreground=fg_color, 
                             font=("Segoe UI", 12, "bold"), borderwidth=1)

    # ----------------------------------------------------
    # UI ROUTING & SIDEBAR
    # ----------------------------------------------------
    def create_sidebar(self):
        self.sidebar = ctk.CTkFrame(self, width=260, corner_radius=0, fg_color=("#FFFFFF", "#18181A"))
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(6, weight=1)

        brand_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        brand_frame.grid(row=0, column=0, padx=20, pady=(30, 20), sticky="w")
        ctk.CTkLabel(brand_frame, text="AEGIS AI", font=self.fonts["h2"], text_color=("#111", "#FFF")).pack(anchor="w")
        ctk.CTkLabel(brand_frame, text="File Architecture Agent", font=self.fonts["small"], text_color=("#666", "#888")).pack(anchor="w")

        self.nav_btns = {}
        nav_items = [("Dashboard", "📊"), ("Organize Workflow", "🚀"), ("Action History", "🕒"), ("Settings & Rules", "⚙️")]
        
        for idx, (name, icon) in enumerate(nav_items):
            btn = ctk.CTkButton(
                self.sidebar, text=f"  {icon}  {name}", anchor="w", 
                fg_color="transparent", hover_color=("#E5E5E5", "#2A2A2D"), 
                text_color=("#333", "#CCC"), font=self.fonts["body_bold"], corner_radius=6,
                command=lambda n=name: self.switch_view(n)
            )
            btn.grid(row=idx+1, column=0, padx=16, pady=4, sticky="ew")
            self.nav_btns[name] = btn

        # Engine Selector (Pinned at bottom)
        bot_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        bot_frame.grid(row=7, column=0, padx=16, pady=20, sticky="ew")
        
        ctk.CTkLabel(bot_frame, text="Active Engine:", font=self.fonts["small"], text_color=("#666", "#888")).pack(anchor="w", pady=(0,4))
        
        self.engine_mode = ctk.CTkSegmentedButton(
            bot_frame, values=["⚡ Fast Smart", "🧠 Gemini AI"], 
            font=self.fonts["small"], command=self.on_mode_change
        )
        self.engine_mode.set(self.config.get("engine_mode", "⚡ Fast Smart"))
        self.engine_mode.pack(fill="x", pady=(0, 10))

        # API Key Entry - Dynamically shows/hides
        self.api_entry = ctk.CTkEntry(bot_frame, placeholder_text="Gemini API Key...", show="*", font=self.fonts["small"])
        self.api_entry.insert(0, self.config.get("api_key", ""))
        self.on_mode_change(self.engine_mode.get()) # Trigger initial check

    def on_mode_change(self, mode):
        """Hides or shows the API Key box based on the active engine."""
        self.config["engine_mode"] = mode
        save_json(CONFIG_FILE, self.config)
        if "Gemini" in mode:
            self.api_entry.pack(fill="x")
        else:
            self.api_entry.pack_forget()

    def switch_view(self, view_name):
        for name, btn in self.nav_btns.items():
            btn.configure(fg_color="#0078D4" if name == view_name else "transparent", 
                          text_color="#FFF" if name == view_name else ("#333", "#CCC"))
            
        for view in self.views.values(): view.grid_remove()
        
        if view_name in self.views:
            self.views[view_name].grid(row=0, column=0, sticky="nsew")
            if view_name == "Dashboard": self.update_dashboard_stats()
            if view_name == "Action History": self.update_history_view()

    # ----------------------------------------------------
    # VIEW: DASHBOARD
    # ----------------------------------------------------
    def create_dashboard_view(self):
        view = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.views["Dashboard"] = view
        view.grid_rowconfigure(2, weight=1)
        view.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(view, fg_color="transparent")
        header.grid(row=0, column=0, padx=40, pady=(40, 20), sticky="ew")
        ctk.CTkLabel(header, text="Workspace Overview", font=self.fonts["h1"]).pack(anchor="w")
        
        target_card = ctk.CTkFrame(view, fg_color=("#FFFFFF", "#252526"), corner_radius=8, border_width=1, border_color=("#E5E5E5", "#333"))
        target_card.grid(row=1, column=0, padx=40, pady=10, sticky="ew")
        target_card.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(target_card, text="Current Target Folder:", font=self.fonts["body_bold"]).grid(row=0, column=0, padx=20, pady=20, sticky="w")
        self.lbl_dash_folder = ctk.CTkLabel(target_card, text=str(self.target_dir), font=self.fonts["body"], text_color="#0078D4")
        self.lbl_dash_folder.grid(row=0, column=1, padx=10, pady=20, sticky="w")
        
        ctk.CTkButton(target_card, text="Change Folder", command=self.change_target_folder, width=120, fg_color=("#E5E5E5", "#333"), text_color=("#000", "#FFF"), hover_color=("#D4D4D4", "#444")).grid(row=0, column=2, padx=20, pady=20)

        stats_frame = ctk.CTkFrame(view, fg_color="transparent")
        stats_frame.grid(row=2, column=0, padx=35, pady=10, sticky="nsew")
        stats_frame.grid_columnconfigure((0,1,2), weight=1)
        
        self.stat_files = self.create_stat_card(stats_frame, "Discovered Files", "0", 0, 0)
        self.stat_size = self.create_stat_card(stats_frame, "Total Size", "0 MB", 0, 1)
        self.stat_history = self.create_stat_card(stats_frame, "Past Organizations", "0", 0, 2)

        action_frame = ctk.CTkFrame(view, fg_color="transparent")
        action_frame.grid(row=3, column=0, padx=40, pady=40, sticky="e")
        ctk.CTkButton(action_frame, text="Start Organization Workflow →", font=self.fonts["h3"], height=45, fg_color="#0078D4", hover_color="#005A9E", command=lambda: self.switch_view("Organize Workflow")).pack()

    def create_stat_card(self, parent, title, value, r, c):
        card = ctk.CTkFrame(parent, fg_color=("#FFFFFF", "#252526"), corner_radius=8, border_width=1, border_color=("#E5E5E5", "#333"))
        card.grid(row=r, column=c, padx=10, pady=10, sticky="nsew")
        ctk.CTkLabel(card, text=title, font=self.fonts["body"], text_color=("#666", "#AAA")).pack(anchor="w", padx=20, pady=(20, 5))
        val_lbl = ctk.CTkLabel(card, text=value, font=self.fonts["h1"])
        val_lbl.pack(anchor="w", padx=20, pady=(0, 20))
        return val_lbl

    def update_dashboard_stats(self):
        self.lbl_dash_folder.configure(text=str(self.target_dir))
        
        def bg_scan():
            if not self.target_dir.exists(): return
            files = [f for f in self.target_dir.iterdir() if f.is_file() and not f.name.startswith('.')]
            total_size = sum(f.stat().st_size for f in files) / (1024*1024)
            history = load_json(HISTORY_FILE, [])
            
            self.after(0, lambda: self.stat_files.configure(text=str(len(files))))
            self.after(0, lambda: self.stat_size.configure(text=f"{total_size:.1f} MB"))
            self.after(0, lambda: self.stat_history.configure(text=str(len(history))))
            
        threading.Thread(target=bg_scan, daemon=True).start()

    def change_target_folder(self):
        selected = filedialog.askdirectory(initialdir=self.target_dir)
        if selected:
            self.target_dir = Path(selected)
            self.config["last_dir"] = str(self.target_dir)
            save_json(CONFIG_FILE, self.config)
            self.update_dashboard_stats()
            self.reset_workflow()

    # ----------------------------------------------------
    # VIEW: ORGANIZE WORKFLOW
    # ----------------------------------------------------
    def create_organize_view(self):
        view = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.views["Organize Workflow"] = view
        view.grid_rowconfigure(2, weight=1)
        view.grid_columnconfigure(0, weight=1)

        self.step_frame = ctk.CTkFrame(view, fg_color=("#FFFFFF", "#1E1E1E"), corner_radius=0, height=60)
        self.step_frame.grid(row=0, column=0, sticky="ew")
        
        self.step_labels = []
        steps = ["01 Select", "02 Analyze", "03 Review Plan", "04 Organize"]
        for i, s in enumerate(steps):
            lbl = ctk.CTkLabel(self.step_frame, text=s, font=self.fonts["h3"], text_color=("#AAA", "#555"))
            lbl.grid(row=0, column=i*2, padx=30, pady=15)
            self.step_labels.append(lbl)
            if i < 3: ctk.CTkLabel(self.step_frame, text="→", text_color=("#AAA", "#555")).grid(row=0, column=i*2+1)

        self.org_status_bar = ctk.CTkFrame(view, fg_color="transparent")
        self.org_status_bar.grid(row=1, column=0, padx=20, pady=(15, 0), sticky="ew")
        self.lbl_org_status = ctk.CTkLabel(self.org_status_bar, text="Ready to scan folder.", font=self.fonts["body_bold"])
        self.lbl_org_status.pack(side="left", padx=10)
        
        self.btn_action = ctk.CTkButton(self.org_status_bar, text="Analyze Files", command=self.run_analysis, fg_color="#0078D4")
        self.btn_action.pack(side="right", padx=10)

        self.workspace = ctk.CTkFrame(view, fg_color="transparent")
        self.workspace.grid(row=2, column=0, padx=20, pady=10, sticky="nsew")
        self.workspace.grid_rowconfigure(0, weight=1)
        self.workspace.grid_columnconfigure(0, weight=3)
        self.workspace.grid_columnconfigure(1, weight=1)

        tree_frame = ctk.CTkFrame(self.workspace, fg_color=("#FFFFFF", "#252526"), corner_radius=8, border_width=1, border_color=("#E5E5E5", "#333"))
        tree_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(tree_frame, columns=("Status", "Confidence"), selectmode="browse")
        self.tree.heading("#0", text="  Proposed Structure", anchor="w")
        self.tree.heading("Status", text="Action", anchor="w")
        self.tree.heading("Confidence", text="Confidence", anchor="w")
        self.tree.column("#0", width=400)
        self.tree.column("Status", width=100, stretch=False)
        self.tree.column("Confidence", width=100, stretch=False)
        self.tree.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        self.details_panel = ctk.CTkFrame(self.workspace, fg_color=("#FFFFFF", "#252526"), corner_radius=8, border_width=1, border_color=("#E5E5E5", "#333"))
        self.details_panel.grid(row=0, column=1, sticky="nsew")
        
        ctk.CTkLabel(self.details_panel, text="File Details", font=self.fonts["h3"]).pack(anchor="w", padx=20, pady=(20, 10))
        self.lbl_det_name = ctk.CTkLabel(self.details_panel, text="Select a file to view details", font=self.fonts["body"], text_color=("#666", "#AAA"), wraplength=250)
        self.lbl_det_name.pack(anchor="w", padx=20, pady=5)
        self.lbl_det_conf = ctk.CTkLabel(self.details_panel, text="", font=self.fonts["body_bold"])
        self.lbl_det_conf.pack(anchor="w", padx=20, pady=5)
        self.lbl_det_reason = ctk.CTkLabel(self.details_panel, text="", font=self.fonts["body"], wraplength=250)
        self.lbl_det_reason.pack(anchor="w", padx=20, pady=5)
        
        self.override_frame = ctk.CTkFrame(self.details_panel, fg_color="transparent")
        ctk.CTkLabel(self.override_frame, text="Change Destination:", font=self.fonts["body_bold"]).pack(anchor="w", pady=(20, 5))
        self.dest_entry = ctk.CTkEntry(self.override_frame, width=200)
        self.dest_entry.pack(anchor="w", pady=5)
        ctk.CTkButton(self.override_frame, text="Update Plan", command=self.update_file_destination, fg_color=("#E5E5E5", "#444"), text_color=("#000", "#FFF")).pack(anchor="w", pady=5)
        
        self.reset_workflow()

    def update_step_ui(self, step):
        self.current_step = step
        for i, lbl in enumerate(self.step_labels):
            if i + 1 == step: lbl.configure(text_color="#0078D4", font=self.fonts["h3"])
            elif i + 1 < step: lbl.configure(text_color=("#107C10", "#2ECC71"), font=self.fonts["h3"])
            else: lbl.configure(text_color=("#AAA", "#555"), font=ctk.CTkFont(family="Segoe UI", size=16))

    def reset_workflow(self):
        """Resets the organize view back to step 1/2 securely."""
        self.organization_plan = []
        self.tree.delete(*self.tree.get_children())
        self.lbl_org_status.configure(text=f"Target: {self.target_dir.name} | Ready to analyze.")
        self.btn_action.configure(text="Analyze Files", command=self.run_analysis, state="normal", fg_color="#0078D4", hover_color="#005A9E")
        self.update_step_ui(2)
        
        self.lbl_det_name.configure(text="Select a file to view details")
        self.lbl_det_conf.configure(text="")
        self.lbl_det_reason.configure(text="")
        self.override_frame.pack_forget()

    # --- CORE ANALYSIS PIPELINE ---
    def run_analysis(self):
        self.update_step_ui(2)
        self.btn_action.configure(state="disabled")
        self.lbl_org_status.configure(text="🔍 Scanning folder and grouping files...")
        
        mode = self.engine_mode.get()
        api_key = self.api_entry.get().strip()
        client = genai.Client(api_key=api_key) if "Gemini" in mode and api_key else None
        
        # Load user-defined exclusions from settings
        raw_excl = self.config.get("exclusions", ".ini, .tmp, .sys")
        excl_set = {x.strip().lower() for x in raw_excl.split(",") if x.strip()}

        def worker():
            all_files = []
            for f in self.target_dir.iterdir():
                if f.is_file() and not f.name.startswith('.') and f.name not in [UNDO_LOG_FILE, CONFIG_FILE, HISTORY_FILE]:
                    if f.name.lower() in excl_set or f.suffix.lower() in excl_set:
                        continue # Safely exclude user-defined files
                    all_files.append(FileRecord(f))

            size_map = {}
            for f in all_files: size_map.setdefault(f.size, []).append(f)
            duplicates, unique_files = [], []
            
            for size, files in size_map.items():
                if len(files) > 1:
                    hash_map = {}
                    for f in files:
                        h = calculate_file_hash(f.path)
                        if h in hash_map: duplicates.append((f, hash_map[h]))
                        else: 
                            hash_map[h] = f
                            unique_files.append(f)
                else: unique_files.append(files[0])

            unique_files.sort(key=lambda x: x.time)
            clusters, current_cluster = [], []
            for f in unique_files:
                if not current_cluster:
                    current_cluster.append(f)
                    continue
                time_gap = (f.time - current_cluster[-1].time) / 60
                domain_match = f.domain in {x.domain for x in current_cluster if x.domain} if f.domain else False
                
                if (domain_match and time_gap <= MAX_MINUTES_RELAXED) or (not domain_match and time_gap <= MAX_MINUTES_STRICT):
                    current_cluster.append(f)
                else:
                    clusters.append(current_cluster)
                    current_cluster = [f]
            if current_cluster: clusters.append(current_cluster)

            self.organization_plan = []
            
            for dup_file, original_file in duplicates:
                self.organization_plan.append({
                    "record": dup_file, "dest_folder": "Review - Duplicates", 
                    "confidence": 100, "reason": f"Exact match of {original_file.name}", 
                    "status": "Will Move"
                })

            for cluster in clusters:
                date_str = datetime.fromtimestamp(cluster[0].time).strftime("%Y-%b-%d")
                
                if len(cluster) == 1:
                    folder = f"Standalone_{cluster[0].ext.replace('.', '').upper()}_Files"
                    conf, reason = 100, "Single file categorization"
                else:
                    if "Gemini" in mode and client:
                        folder, conf, reason = heuristic_cluster_naming(cluster, date_str) 
                    else:
                        folder, conf, reason = heuristic_cluster_naming(cluster, date_str)
                
                for f in cluster:
                    self.organization_plan.append({
                        "record": f, "dest_folder": folder, 
                        "confidence": conf, "reason": reason, "status": "Will Move"
                    })

            self.after(0, self.render_plan_preview)

        threading.Thread(target=worker, daemon=True).start()

    def render_plan_preview(self):
        self.tree.delete(*self.tree.get_children())
        self.tree_item_map = {} 
        
        folder_groups = {}
        for idx, item in enumerate(self.organization_plan):
            folder_groups.setdefault(item["dest_folder"], []).append((idx, item))

        low_confidence_count = 0
        for folder, items in folder_groups.items():
            f_id = self.tree.insert("", "end", text=f" 📂 {folder}", values=("Folder", ""))
            for idx, item in items:
                rec = item["record"]
                conf_str = f"{item['confidence']}%"
                icon = "🔒" if item["confidence"] < 50 else "📄"
                if item["confidence"] < 50: low_confidence_count += 1
                
                i_id = self.tree.insert(f_id, "end", text=f"   {icon} {rec.name}", values=(item["status"], conf_str))
                self.tree_item_map[i_id] = idx

        summary = f"Plan ready: {len(self.organization_plan)} files into {len(folder_groups)} folders."
        if low_confidence_count: summary += f" ⚠ {low_confidence_count} need review."
        
        self.lbl_org_status.configure(text=summary)
        self.update_step_ui(3)
        self.btn_action.configure(text="Execute & Organize", command=self.run_execution, state="normal", fg_color="#107C10", hover_color="#0B5A0B")

    def on_tree_select(self, event):
        selected = self.tree.selection()
        if not selected: return
        item_id = selected[0]
        
        if item_id in self.tree_item_map:
            idx = self.tree_item_map[item_id]
            plan = self.organization_plan[idx]
            rec = plan["record"]
            
            self.lbl_det_name.configure(text=f"Name: {rec.name}\nSize: {rec.size/1024:.1f} KB")
            c_color = "#2ECC71" if plan["confidence"] >= 80 else ("#E67E22" if plan["confidence"] >= 50 else "#E74C3C")
            self.lbl_det_conf.configure(text=f"Confidence: {plan['confidence']}%", text_color=c_color)
            self.lbl_det_reason.configure(text=f"Reason:\n{plan['reason']}")
            
            self.override_frame.pack(anchor="w", padx=20, pady=20)
            self.dest_entry.delete(0, 'end')
            self.dest_entry.insert(0, plan["dest_folder"])
            self.selected_plan_idx = idx
        else:
            self.override_frame.pack_forget()
            self.lbl_det_name.configure(text="Folder Details\nExpand to see files.")
            self.lbl_det_conf.configure(text="")
            self.lbl_det_reason.configure(text="")

    def update_file_destination(self):
        new_dest = self.dest_entry.get().strip()
        if new_dest and hasattr(self, 'selected_plan_idx'):
            self.organization_plan[self.selected_plan_idx]["dest_folder"] = new_dest
            self.organization_plan[self.selected_plan_idx]["reason"] = "Manual User Override"
            self.organization_plan[self.selected_plan_idx]["confidence"] = 100
            self.render_plan_preview()

    # --- EXECUTION PIPELINE ---
    def run_execution(self):
        if not messagebox.askyesno("Confirm Move", "Execute this plan? Files will be physically moved. This can be undone later."): return
        
        self.update_step_ui(4)
        self.btn_action.configure(state="disabled")
        self.lbl_org_status.configure(text="🚀 Executing transactional file moves...")
        
        def worker():
            undo_log = []
            success_count = 0
            
            for item in self.organization_plan:
                if item["status"] != "Will Move": continue
                
                src = item["record"].path
                dest_dir = self.target_dir / item["dest_folder"]
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest = dest_dir / src.name
                
                try:
                    safe_move(src, dest)
                    undo_log.append({"original": str(src), "new": str(dest)})
                    success_count += 1
                except Exception as e:
                    print(f"Failed to move {src.name}: {e}")

            if undo_log:
                save_json(self.target_dir / UNDO_LOG_FILE, undo_log)
                history = load_json(HISTORY_FILE, [])
                history.append({
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "target": str(self.target_dir),
                    "files_moved": success_count,
                    "folders_created": len(set(i["dest_folder"] for i in self.organization_plan))
                })
                save_json(HISTORY_FILE, history)

            self.after(0, lambda: self.lbl_org_status.configure(text=f"✅ Success! {success_count} files moved safely."))
            # Reset button safely provides a way out of the "Done" state
            self.after(0, lambda: self.btn_action.configure(text="Start New Analysis", command=self.reset_workflow, state="normal", fg_color="#0078D4", hover_color="#005A9E"))

        threading.Thread(target=worker, daemon=True).start()

    # ----------------------------------------------------
    # VIEW: SETTINGS & RULES
    # ----------------------------------------------------
    def create_settings_view(self):
        view = ctk.CTkScrollableFrame(self.main_container, fg_color="transparent")
        self.views["Settings & Rules"] = view
        
        header = ctk.CTkFrame(view, fg_color="transparent")
        header.pack(fill="x", padx=40, pady=(40, 20))
        ctk.CTkLabel(header, text="Settings & Rules", font=self.fonts["h1"]).pack(side="left")
        
        # --- Appearance Panel ---
        app_frame = ctk.CTkFrame(view, fg_color=("#FFFFFF", "#252526"), corner_radius=8, border_width=1, border_color=("#E5E5E5", "#333"))
        app_frame.pack(fill="x", padx=40, pady=10)
        ctk.CTkLabel(app_frame, text="Appearance", font=self.fonts["h3"]).pack(anchor="w", padx=20, pady=(20, 10))
        
        theme_switch = ctk.CTkSegmentedButton(app_frame, values=["System", "Dark", "Light"], command=self.change_theme)
        theme_switch.set(self.config.get("theme", "System"))
        theme_switch.pack(anchor="w", padx=20, pady=(0, 20))
        
        # --- Exclusions Panel ---
        excl_frame = ctk.CTkFrame(view, fg_color=("#FFFFFF", "#252526"), corner_radius=8, border_width=1, border_color=("#E5E5E5", "#333"))
        excl_frame.pack(fill="x", padx=40, pady=10)
        ctk.CTkLabel(excl_frame, text="File Exclusions", font=self.fonts["h3"]).pack(anchor="w", padx=20, pady=(20, 10))
        ctk.CTkLabel(excl_frame, text="Comma separated list of filenames or extensions to ignore (e.g., .ini, hidden.txt, .tmp)", font=self.fonts["small"], text_color=("#666", "#AAA")).pack(anchor="w", padx=20, pady=(0, 10))
        
        self.excl_text = ctk.CTkTextbox(excl_frame, height=80, font=self.fonts["body"])
        self.excl_text.pack(fill="x", padx=20, pady=(0, 10))
        default_excl = self.config.get("exclusions", ".ini, .tmp, .sys")
        self.excl_text.insert("1.0", default_excl)
        
        ctk.CTkButton(excl_frame, text="Save Exclusions", command=self.save_exclusions, fg_color="#0078D4").pack(anchor="w", padx=20, pady=(0, 20))

        # Apply user theme on start
        self.change_theme(self.config.get("theme", "System"))

    def change_theme(self, mode):
        ctk.set_appearance_mode(mode)
        self.config["theme"] = mode
        save_json(CONFIG_FILE, self.config)
        
    def save_exclusions(self):
        excl = self.excl_text.get("1.0", "end").strip()
        self.config["exclusions"] = excl
        save_json(CONFIG_FILE, self.config)
        messagebox.showinfo("Saved", "Exclusion rules saved successfully.")

    # ----------------------------------------------------
    # VIEW: HISTORY & UNDO
    # ----------------------------------------------------
    def create_history_view(self):
        view = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.views["Action History"] = view
        
        header = ctk.CTkFrame(view, fg_color="transparent")
        header.pack(fill="x", padx=40, pady=(40, 20))
        ctk.CTkLabel(header, text="Organization History", font=self.fonts["h1"]).pack(side="left")
        
        self.btn_run_undo = ctk.CTkButton(header, text="↩️ Undo Last Local Run", fg_color="transparent", border_width=1, border_color="#D13438", text_color="#D13438", hover_color=("#FDE7E9", "#4A191B"), command=self.run_undo)
        self.btn_run_undo.pack(side="right")

        self.history_scroll = ctk.CTkScrollableFrame(view, fg_color="transparent")
        self.history_scroll.pack(fill="both", expand=True, padx=30, pady=10)

    def update_history_view(self):
        for w in self.history_scroll.winfo_children(): w.destroy()
        
        history = load_json(HISTORY_FILE, [])
        if not history:
            ctk.CTkLabel(self.history_scroll, text="No history recorded yet.", font=self.fonts["body"]).pack(pady=40)
            return
            
        for session in reversed(history):
            card = ctk.CTkFrame(self.history_scroll, fg_color=("#FFFFFF", "#252526"), corner_radius=8, border_width=1, border_color=("#E5E5E5", "#333"))
            card.pack(fill="x", padx=10, pady=8)
            
            ctk.CTkLabel(card, text=f"📅 {session['date']}", font=self.fonts["body_bold"]).grid(row=0, column=0, padx=20, pady=10, sticky="w")
            ctk.CTkLabel(card, text=f"Folder: {session['target']}", font=self.fonts["small"]).grid(row=1, column=0, padx=20, pady=(0,10), sticky="w")
            
            ctk.CTkLabel(card, text=f"{session['files_moved']} Files Organized", font=self.fonts["body_bold"], text_color="#0078D4").grid(row=0, column=1, rowspan=2, padx=20, pady=10, sticky="e")
            card.grid_columnconfigure(1, weight=1)

    def run_undo(self):
        log_path = self.target_dir / UNDO_LOG_FILE
        if not log_path.exists():
            messagebox.showwarning("No History", "No recent organization found in the current target folder to undo.")
            return

        if not messagebox.askyesno("Confirm Undo", "This will revert the last organization run in this folder. Proceed?"): return
        
        def worker():
            undo_log = load_json(log_path, [])
            folders_to_check, restored_count = set(), 0

            for item in undo_log:
                new_path, original_path = Path(item["new"]), Path(item["original"])
                if new_path.exists():
                    safe_move(new_path, original_path)
                    folders_to_check.add(new_path.parent)
                    restored_count += 1

            for folder in folders_to_check:
                try:
                    if not any(folder.iterdir()): folder.rmdir()
                except: pass

            log_path.unlink()
            self.after(0, lambda: messagebox.showinfo("Undo Complete", f"Restored {restored_count} files successfully."))
            self.after(0, self.update_history_view)
            self.after(0, self.reset_workflow) # Ensures ghost-states are completely erased
            self.after(0, self.update_dashboard_stats)

        threading.Thread(target=worker, daemon=True).start()

if __name__ == "__main__":
    app = AegisAgentApp()
    app.mainloop()