import os
import shutil
import json
import time
import threading
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse
import re
from collections import Counter

import customtkinter as ctk
from tkinter import messagebox, filedialog

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
# ⚙️ SETTINGS & CONFIGURATION
# ==========================================
MAX_MINUTES_STRICT = 5    
MAX_MINUTES_RELAXED = 30  
UNDO_LOG_FILE = "agent_undo_log.json"
CONFIG_FILE = "aegis_config.json"

NOISE_WORDS = {
    "screencapture", "screenshot", "snip", "dashboard", "download", "downloads",
    "image", "img", "file", "document", "copy", "new", "untitled", "preview",
    "page", "report", "final", "temp", "tmp", "edit", "result", "details", "login",
    "aspx", "html", "php", "index", "www", "com", "org", "net", "app", "io", "en", "us",
    "review", "module", "summary", "profile", "history", "compose", "mail"
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f: return json.load(f)
        except Exception: return {}
    return {}

def save_config(data):
    with open(CONFIG_FILE, "w") as f: json.dump(data, f)

# ==========================================
# 🧠 FILE INTELLIGENCE & HEURISTICS
# ==========================================
def extract_screencapture_domain(filename):
    match = re.search(r"screencapture-([a-zA-Z0-9.-]+)", filename, re.IGNORECASE)
    if match:
        raw_slug = match.group(1)
        tokens = [t for t in re.split(r"[-._]", raw_slug) if t.lower() not in {"com", "org", "net", "in", "io", "app"}]
        clean_tokens = [t for t in tokens if not (len(t) >= 8 and any(c.isupper() for c in t) and any(c.islower() for c in t) and any(c.isdigit() for c in t))]
        if clean_tokens:
            return clean_tokens[0].lower()
    return None

class FileRecord:
    def __init__(self, path):
        self.path = path
        self.name = path.name
        self.ext = path.suffix.lower()
        self.time = path.stat().st_mtime 
        self.is_screenshot = any(w in self.name.lower() for w in ["screenshot", "snip", "screencapture"])
        
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
        except FileNotFoundError: pass
        return None

def safe_move(src_path, dest_path):
    src_path, dest_path = Path(src_path), Path(dest_path)
    stat = src_path.stat()
    original_atime, original_mtime = stat.st_atime, stat.st_mtime
    shutil.move(str(src_path), str(dest_path))
    os.utime(str(dest_path), (original_atime, original_mtime))

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

    if primary_source and topic: folder_name = f"{primary_source} - {topic}"
    elif primary_source: folder_name = primary_source
    elif topic: folder_name = topic
    else:
        types = list({f.ext.replace('.', '').upper() for f in cluster if f.ext})
        folder_name = f"{' & '.join(types[:2])} Files" if types else "Session Files"

    folder_name = folder_name[:45].strip()
    return f"{date_str}_{folder_name}"

# ==========================================
# 🎨 FLUENT UI COMPONENTS
# ==========================================
class HoverTooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip_window = None
        self.schedule_id = None
        
        self.widget.bind("<Enter>", self.schedule_show)
        self.widget.bind("<Leave>", self.hide_tooltip)
        self.widget.bind("<ButtonPress>", self.hide_tooltip)

    def schedule_show(self, event=None):
        self.hide_tooltip() 
        self.schedule_id = self.widget.after(350, self.show_tooltip)

    def show_tooltip(self):
        if self.tooltip_window: return
        x = self.widget.winfo_rootx() + self.widget.winfo_width() + 15
        y = self.widget.winfo_rooty() + (self.widget.winfo_height() // 2) - 15
        
        self.tooltip_window = ctk.CTkToplevel(self.widget)
        self.tooltip_window.wm_overrideredirect(True)
        self.tooltip_window.wm_geometry(f"+{x}+{y}")
        self.tooltip_window.attributes('-topmost', True)
        
        # WinUI styled tooltip
        label = ctk.CTkLabel(
            self.tooltip_window, text=self.text, 
            fg_color=("#FFFFFF", "#2B2B2B"), 
            text_color=("#111111", "#FFFFFF"),
            corner_radius=6, padx=12, pady=6, 
            font=ctk.CTkFont(family="Segoe UI", size=12)
        )
        label.pack()

    def hide_tooltip(self, event=None):
        if self.schedule_id:
            self.widget.after_cancel(self.schedule_id)
            self.schedule_id = None
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None

# ==========================================
# 🖥️ MAIN APPLICATION
# ==========================================
# Use system mode to automatically handle Light/Dark transitions
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

class AegisAgentApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Aegis - Intelligent File Architecture")
        self.geometry("1150x780")
        self.config_data = load_config()
        self.target_dir = None
        self.rules_visible = False
        
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # Global Font Definitions (WinUI/Fluent Style)
        self.font_header = ctk.CTkFont(family="Segoe UI", size=24, weight="bold")
        self.font_subheader = ctk.CTkFont(family="Segoe UI", size=13, weight="bold")
        self.font_body = ctk.CTkFont(family="Segoe UI", size=13)
        self.font_body_small = ctk.CTkFont(family="Segoe UI", size=12)
        self.font_card_title = ctk.CTkFont(family="Segoe UI", size=15, weight="bold")

        self.create_sidebar()
        self.create_main_area()
        self.check_initial_setup()

    def check_initial_setup(self):
        saved_dir = self.config_data.get("last_dir")
        if saved_dir and os.path.exists(saved_dir):
            self.target_dir = Path(saved_dir)
            self.update_folder_ui()
        else:
            self.toggle_action_buttons("disabled")

    def create_sidebar(self):
        # Sidebar with slightly distinct background from main area
        self.sidebar = ctk.CTkFrame(self, width=280, corner_radius=0, fg_color=("#FFFFFF", "#1C1C1C"))
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(12, weight=1)

        self.logo = ctk.CTkLabel(self.sidebar, text="AEGIS AI", font=self.font_header, text_color=("#111111", "#FFFFFF"))
        self.logo.grid(row=0, column=0, padx=20, pady=(25, 4))
        self.sub_logo = ctk.CTkLabel(self.sidebar, text="File Architecture Agent", font=self.font_body_small, text_color=("#555555", "#A0A0A0"))
        self.sub_logo.grid(row=1, column=0, padx=20, pady=(0, 25))

        self.lbl_folder = ctk.CTkLabel(self.sidebar, text="⚠️ No Folder Selected", font=self.font_subheader, text_color="#D13438")
        self.lbl_folder.grid(row=2, column=0, padx=20, pady=(5, 5))
        
        # Primary Action: Windows 11 Blue
        self.btn_folder = ctk.CTkButton(
            self.sidebar, text="📂 Select Target Folder", command=self.change_folder, 
            fg_color="#0078D4", hover_color="#005A9E", corner_radius=6, font=self.font_body
        )
        self.btn_folder.grid(row=3, column=0, padx=20, pady=(0, 20), sticky="ew")
        HoverTooltip(self.btn_folder, "Select the folder to organize (e.g., Downloads).")

        self.lbl_mode = ctk.CTkLabel(self.sidebar, text="Naming Engine:", font=self.font_subheader, text_color=("#333333", "#BBBBBB"))
        self.lbl_mode.grid(row=4, column=0, padx=20, pady=(15, 2), sticky="w")

        self.naming_mode = ctk.CTkSegmentedButton(
            self.sidebar, values=["⚡ Fast Smart", "🧠 Gemini AI"], command=self.on_mode_change,
            selected_color="#0078D4", selected_hover_color="#005A9E", corner_radius=6, font=self.font_body
        )
        self.naming_mode.set("⚡ Fast Smart")
        self.naming_mode.grid(row=5, column=0, padx=20, pady=(0, 10), sticky="ew")
        HoverTooltip(self.lbl_mode, "⚡ Fast Smart: Instant, offline pattern matching.\n🧠 Gemini AI: Multimodal vision & document reading (Slower).")

        saved_key = self.config_data.get("api_key", "")
        self.api_entry = ctk.CTkEntry(
            self.sidebar, placeholder_text="Gemini API Key...", show="*", 
            corner_radius=6, font=self.font_body
        )
        self.api_entry.insert(0, saved_key)
        HoverTooltip(self.api_entry, "Get a free key from Google AI Studio.")
        self.on_mode_change(self.naming_mode.get())

        # Secondary Action: Neutral System Adapting Colors
        self.btn_dry = ctk.CTkButton(
            self.sidebar, text="🔍 Preview Organization", command=self.start_dry_run, 
            fg_color=("#E5E5E5", "#333333"), hover_color=("#D4D4D4", "#444444"), 
            text_color=("#111111", "#FFFFFF"), corner_radius=6, font=self.font_body
        )
        self.btn_dry.grid(row=7, column=0, padx=20, pady=(25, 8), sticky="ew")
        HoverTooltip(self.btn_dry, "Generates folder names and displays file cards.\nNO files are moved.")

        # Primary Action: Windows 11 Blue
        self.btn_exec = ctk.CTkButton(
            self.sidebar, text="🚀 Execute & Move", command=self.start_execution, 
            fg_color="#0078D4", hover_color="#005A9E", text_color="#FFFFFF",
            corner_radius=6, font=self.font_body
        )
        self.btn_exec.grid(row=8, column=0, padx=20, pady=8, sticky="ew")
        HoverTooltip(self.btn_exec, "Moves files to organized folders.\nMetadata (timestamps) is 100% preserved.")

        # Destructive Action: Subtle Outline
        self.btn_undo = ctk.CTkButton(
            self.sidebar, text="↩️ Undo Last Run", command=self.start_undo, 
            fg_color="transparent", border_width=1, border_color="#D13438", 
            text_color="#D13438", hover_color=("#FDE7E9", "#4A191B"), 
            corner_radius=6, font=self.font_body
        )
        self.btn_undo.grid(row=9, column=0, padx=20, pady=8, sticky="ew")
        HoverTooltip(self.btn_undo, "Restores all files back to their exact original locations.")

        # Expandable Safety Rules Accordion
        self.btn_rules_toggle = ctk.CTkButton(
            self.sidebar, text="▶ Precautions & Rules", command=self.toggle_rules, 
            fg_color="transparent", hover_color=("#E5E5E5", "#2A2A2D"), 
            text_color=("#555555", "#AAAAAA"), anchor="w", corner_radius=6, font=self.font_body
        )
        self.btn_rules_toggle.grid(row=10, column=0, padx=20, pady=(20, 0), sticky="ew")
        
        self.rules_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        rules_text = "1. ZERO DELETIONS: Files are never deleted.\n2. METADATA SAFE: Creation times preserved.\n3. SMART CLUSTERS: Groups by web origin & time."
        self.lbl_rules = ctk.CTkLabel(
            self.rules_frame, text=rules_text, justify="left", 
            font=self.font_body_small, text_color=("#666666", "#777777")
        )
        self.lbl_rules.pack(padx=16, pady=4, anchor="nw")
        self.rules_frame.grid(row=11, column=0, padx=20, pady=0, sticky="ew")
        self.rules_frame.grid_remove() 

        self.btn_shortcut = ctk.CTkButton(
            self.sidebar, text="🔗 Create Desktop Shortcut", command=self.create_shortcut, 
            fg_color="transparent", border_width=1, border_color=("#CCCCCC", "#444444"),
            text_color=("#555555", "#AAAAAA"), corner_radius=6, font=self.font_body
        )
        self.btn_shortcut.grid(row=13, column=0, padx=20, pady=20, sticky="ew")

    def toggle_rules(self):
        if self.rules_visible:
            self.rules_frame.grid_remove()
            self.btn_rules_toggle.configure(text="▶ Precautions & Rules")
            self.rules_visible = False
        else:
            self.rules_frame.grid()
            self.btn_rules_toggle.configure(text="▼ Precautions & Rules")
            self.rules_visible = True

    def on_mode_change(self, mode):
        if "Gemini" in mode:
            self.api_entry.grid(row=6, column=0, padx=20, pady=(0, 16), sticky="ew")
        else:
            self.api_entry.grid_remove() 

    def create_main_area(self):
        # Deep slate in dark mode, off-white in light mode
        self.main_area = ctk.CTkFrame(self, fg_color=("#F3F3F3", "#202020"), corner_radius=0)
        self.main_area.grid(row=0, column=1, sticky="nsew")
        self.main_area.grid_rowconfigure(2, weight=1)
        self.main_area.grid_columnconfigure(0, weight=1)

        self.header_frame = ctk.CTkFrame(self.main_area, fg_color="transparent")
        self.header_frame.grid(row=0, column=0, padx=32, pady=(28, 8), sticky="ew")
        
        self.lbl_status = ctk.CTkLabel(
            self.header_frame, text="Ready for Instructions", 
            font=self.font_header, text_color=("#111111", "#FFFFFF")
        )
        self.lbl_status.pack(side="left")

        # WinUI 3 Progress Bar styling
        self.progress = ctk.CTkProgressBar(self.main_area, mode="indeterminate", height=4, progress_color="#0078D4")
        self.progress.grid(row=1, column=0, padx=32, pady=8, sticky="ew")
        self.progress.set(0)

        self.results_scroll = ctk.CTkScrollableFrame(self.main_area, fg_color="transparent")
        self.results_scroll.grid(row=2, column=0, padx=24, pady=(8, 24), sticky="nsew")

    def change_folder(self):
        selected = filedialog.askdirectory(initialdir=Path.home())
        if selected:
            self.target_dir = Path(selected)
            self.update_folder_ui()

    def update_folder_ui(self):
        self.lbl_folder.configure(text=f"Target: {self.target_dir.name}", text_color=("#107C10", "#2ECC71"))
        self.config_data["last_dir"] = str(self.target_dir)
        save_config(self.config_data)
        self.toggle_action_buttons("normal")

    def toggle_action_buttons(self, state):
        self.btn_dry.configure(state=state)
        self.btn_exec.configure(state=state)
        self.btn_undo.configure(state=state)
        if state == "disabled": self.progress.start()
        else: self.progress.stop()

    def clear_results(self):
        for widget in self.results_scroll.winfo_children(): widget.destroy()

    def add_result_card(self, folder_name, files):
        # Modern Card styling: Pure white or slightly elevated dark gray, subtle border, 8px radius
        card = ctk.CTkFrame(
            self.results_scroll, corner_radius=8, 
            fg_color=("#FFFFFF", "#2B2B2B"), 
            border_width=1, border_color=("#E5E5E5", "#3F3F3F")
        )
        card.pack(fill="x", padx=8, pady=8)
        
        header = ctk.CTkLabel(
            card, text=f"📂 {folder_name}", font=self.font_card_title, text_color=("#0078D4", "#58A6FF")
        )
        header.pack(anchor="w", padx=16, pady=(12, 4))
        
        for f in files:
            name = f.name if hasattr(f, 'name') else f.parts[-1]
            domain = f.domain if hasattr(f, 'domain') else None
            source_tag = f" (🌐 {domain})" if domain else ""
            
            file_lbl = ctk.CTkLabel(
                card, text=f"   • {name}{source_tag}", 
                font=self.font_body, text_color=("#333333", "#CCCCCC")
            )
            file_lbl.pack(anchor="w", padx=16, pady=2)
            
        ctk.CTkFrame(card, height=12, fg_color="transparent").pack()

    def get_ai_client(self):
        api_key = self.api_entry.get().strip()
        if not api_key: return None
        self.config_data["api_key"] = api_key
        save_config(self.config_data)
        return genai.Client(api_key=api_key)

    def start_dry_run(self):
        threading.Thread(target=self.run_organization, args=(True,), daemon=True).start()

    def start_execution(self):
        if messagebox.askyesno("Confirm Move", "This will physically organize and move files into new folders. Continue?"):
            threading.Thread(target=self.run_organization, args=(False,), daemon=True).start()

    def start_undo(self):
        threading.Thread(target=self.run_undo, daemon=True).start()

    def analyze_cluster_gemini(self, cluster, date_prefix, ai_client):
        contents = []
        text_context = "Files in session:\n"
        for f in cluster:
            text_context += f"- {f.name} (Source: {f.domain})\n"
            if f.ext == ".pdf":
                try:
                    with open(f.path, "rb") as pdf_file:
                        reader = PyPDF2.PdfReader(pdf_file)
                        extracted = "".join(p.extract_text() for p in reader.pages[:2])
                        text_context += f"   [Content]: {extracted[:400]}\n"
                except: pass
            elif f.ext in [".png", ".jpg", ".jpeg"] and f.is_screenshot:
                try:
                    img = Image.open(f.path)
                    img.thumbnail((700, 700))
                    contents.append(img)
                except: pass

        prompt = f"""You are an expert file organizer. Examine the files.
        Reply ONLY with format: "Website - Purpose" (e.g. "Nvidia - Account Details"). Do NOT include slashes or punctuation.
        {text_context}"""
        contents.insert(0, prompt)
        try:
            time.sleep(3)
            response = ai_client.models.generate_content(model='gemini-2.5-flash', contents=contents)
            clean_name = re.sub(r'[\\/*?:"<>|\n\r]', "", response.text.strip())
            return f"{date_prefix}_{clean_name}"
        except: return heuristic_cluster_naming(cluster, date_prefix)

    def scan_and_group(self):
        all_files = []
        for f in self.target_dir.iterdir():
            if f.is_file() and f.name not in [Path(__file__).name, UNDO_LOG_FILE, CONFIG_FILE] and not f.name.startswith('.'):
                all_files.append(FileRecord(f))
                
        all_files.sort(key=lambda x: x.time)
        clusters, current_cluster = [], []
        
        for file in all_files:
            if not current_cluster:
                current_cluster.append(file)
                continue
            last_file = current_cluster[-1]
            time_gap = (file.time - last_file.time) / 60
            domain_match = file.domain in {f.domain for f in current_cluster if f.domain} if file.domain else False

            if (domain_match and time_gap <= MAX_MINUTES_RELAXED) or (not domain_match and time_gap <= MAX_MINUTES_STRICT):
                current_cluster.append(file)
            else:
                clusters.append(current_cluster)
                current_cluster = [file]

        if current_cluster: clusters.append(current_cluster)

        safe_clusters = []
        for cluster in clusters:
            if len(cluster) > 20:
                has_web_origins = any(f.domain for f in cluster)
                if not has_web_origins:
                    type_dict = {}
                    for f in cluster: type_dict.setdefault(f.ext, []).append(f)
                    for ext_group in type_dict.values(): safe_clusters.append(ext_group)
                    continue
            safe_clusters.append(cluster)

        return safe_clusters

    def run_organization(self, dry_run=True):
        self.after(0, lambda: self.toggle_action_buttons("disabled"))
        self.after(0, lambda: self.clear_results())
        
        mode = self.naming_mode.get()
        ai_client = self.get_ai_client() if "Gemini" in mode else None

        clusters = self.scan_and_group()
        if not clusters:
            self.after(0, lambda: self.lbl_status.configure(text="✅ Folder is already organized!"))
            self.after(0, lambda: self.toggle_action_buttons("normal"))
            return

        total_files = sum(len(c) for c in clusters)
        total_folders = len(clusters)
        
        msg = f"🔍 Scanning {total_files} files..." if dry_run else f"🚀 Organizing {total_files} files..."
        self.after(0, lambda m=msg: self.lbl_status.configure(text=m))

        undo_log = []
        for cluster in clusters:
            date_str = datetime.fromtimestamp(cluster[0].time).strftime("%Y-%b-%d")
            
            if len(cluster) == 1:
                folder_name = f"Standalone_{cluster[0].ext.replace('.', '').upper()}_Files"
                dest_folder = self.target_dir / "Standalone_Files" / folder_name
            else:
                if "Gemini" in mode and ai_client:
                    folder_name = self.analyze_cluster_gemini(cluster, date_str, ai_client)
                else:
                    folder_name = heuristic_cluster_naming(cluster, date_str)
                dest_folder = self.target_dir / folder_name

            self.after(0, lambda name=dest_folder.name, c=cluster: self.add_result_card(name, c))

            if not dry_run:
                dest_folder.mkdir(parents=True, exist_ok=True)
                for f in cluster:
                    new_path = dest_folder / f.name
                    safe_move(f.path, new_path)
                    undo_log.append({"original": str(f.path), "new": str(new_path)})

        if not dry_run and undo_log:
            with open(self.target_dir / UNDO_LOG_FILE, "w") as f: json.dump(undo_log, f)
            final_msg = f"✅ Success: {total_files} files organized into {total_folders} folders."
            self.after(0, lambda m=final_msg: self.lbl_status.configure(text=m))
            self.after(0, lambda: messagebox.showinfo("Success", "Organization Complete!"))
        elif dry_run:
            preview_msg = f"✅ Preview Plan: {total_files} files will be organized into {total_folders} folders."
            self.after(0, lambda m=preview_msg: self.lbl_status.configure(text=m))

        self.after(0, lambda: self.toggle_action_buttons("normal"))

    def run_undo(self):
        log_path = self.target_dir / UNDO_LOG_FILE
        if not log_path.exists():
            self.after(0, lambda: messagebox.showwarning("No History", "No recent organization found to undo."))
            return

        self.after(0, lambda: self.toggle_action_buttons("disabled"))
        self.after(0, lambda: self.lbl_status.configure(text="⏪ Reverting..."))
        self.after(0, lambda: self.clear_results())

        with open(log_path, "r") as f: undo_log = json.load(f)
        folders_to_check, restored_files = set(), []

        for item in undo_log:
            new_path, original_path = Path(item["new"]), Path(item["original"])
            if new_path.exists():
                safe_move(new_path, original_path)
                folders_to_check.add(new_path.parent)
                restored_files.append(original_path)

        for folder in folders_to_check:
            try:
                if not any(folder.iterdir()): folder.rmdir()
            except: pass

        log_path.unlink()
        
        undo_msg = f"✅ Undo Complete: {len(restored_files)} files restored from {len(folders_to_check)} folders."
        self.after(0, lambda: self.add_result_card("Restored Files", restored_files))
        self.after(0, lambda m=undo_msg: self.lbl_status.configure(text=m))
        self.after(0, lambda: self.toggle_action_buttons("normal"))

    def create_shortcut(self):
        try:
            desktop = os.path.join(os.environ["USERPROFILE"], "Desktop")
            shortcut_path = os.path.join(desktop, "Aegis File Organizer.lnk")
            target_script = os.path.abspath(__file__)
            python_exe = "pythonw.exe"

            vbs_script = f'''
            Set oWS = WScript.CreateObject("WScript.Shell")
            sLinkFile = "{shortcut_path}"
            Set oLink = oWS.CreateShortcut(sLinkFile)
            oLink.TargetPath = "{python_exe}"
            oLink.Arguments = """{target_script}"""
            oLink.WorkingDirectory = """{os.path.dirname(target_script)}"""
            oLink.Description = "Aegis AI Organizer"
            oLink.Save
            '''
            vbs_path = os.path.join(os.environ["TEMP"], "create_shortcut.vbs")
            with open(vbs_path, "w") as f: f.write(vbs_script)
            os.system(f'cscript //nologo "{vbs_path}"')
            messagebox.showinfo("Success", "Shortcut created on your Desktop!")
        except Exception as e:
            messagebox.showerror("Error", f"Could not create shortcut: {e}")

if __name__ == "__main__":
    app = AegisAgentApp()
    app.mainloop()