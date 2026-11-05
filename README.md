🛡️ Aegis — Intelligent File Architecture Agent
<p align="center">
  <strong>Turn a cluttered folder into a clear, structured workspace.</strong><br>
  A desktop file-organization assistant with local smart rules and optional Gemini AI analysis.
</p><p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/Interface-CustomTkinter-2E8B57" alt="CustomTkinter">
  <img src="https://img.shields.io/badge/AI-Google%20Gemini-orange" alt="Google Gemini">
  <img src="https://img.shields.io/badge/Platform-Windows%20focused-0078D4?logo=windows&logoColor=white" alt="Windows focused">
  <img src="https://img.shields.io/badge/Version-1.3.0-6f42c1" alt="Version 1.3.0 shown in Agent-2 screenshot">
</p>Aegis is a Python desktop application that helps you organize files into meaningful folders. Choose a target folder, select a naming engine, review the proposed folder structure, and then run the organization. The application also provides organization history and an option to undo the last run.
The screenshots below show two Aegis interface iterations. Agent-2 is the dashboard-first interface; Agent-1 is the earlier guided workflow. Both are included so the README reflects the supplied application screens.

Contents
- Highlights
- AI and naming engines
- How it works
- Application screens
- Requirements
- Installation and launch
- Safety and privacy
- Troubleshooting
✨ Highlights
Feature	What it does
Two naming engines	Choose Fast Smart for local, rule-based grouping or Gemini AI for online, context-aware analysis.
Folder analysis	Analyze a selected target folder and build a proposed organization plan.
Review before organizing	Inspect the proposed folder structure before executing the move. The Agent-2 analysis screen includes Action and Confidence columns, plus a file-details panel.
Workspace dashboard	View the selected target folder, discovered-file count, total size, and past-organization count.
Organization history	Review previous organization activity through the Action History area.
Undo support	Revert the most recent organization run using the application's JSON-based history ledger and undo feature.
File metadata care	The project description specifies preservation of file creation and modification timestamps.
Modern desktop interface	Built with CustomTkinter, with Light/Dark mode support, WinUI 3-inspired typography, hover tooltips, and background processing to keep the interface responsive.


🧠 AI and naming engines
Aegis offers two approaches to naming and grouping files. Choose the engine that fits the folder and the level of analysis you need.
Fast Smart — local analysis
- Works as the local/offline naming option described by the project.
- Uses regular expressions and Windows Zone.Identifier alternate data streams.
- Uses available download-origin and timing information to help group related downloaded files.
- A practical choice when you prefer local processing and quick rule-based organization.
Gemini AI — online analysis
- Uses Google's Gemini 2.5 Flash multimodal AI, as described in the original project README.
- Can analyze supported content such as PDFs, Word documents, and screenshots.
- Uses document and image context to suggest more meaningful, semantic folder names.
- Requires internet connectivity and the Gemini integration to be configured in the project.
Choosing an engine: Use Fast Smart for local rule-based grouping. Choose Gemini AI when document or screenshot context is useful for deciding where files belong.
🔄 How it works
The workflow is designed to let you inspect the plan before files are moved.
1. Select a target folder — Choose the folder that contains the files you want Aegis to organize.
2. Choose a naming engine — Select Fast Smart or Gemini AI.
3. Analyze the files — Start the analysis to identify files and propose a folder structure.
4. Review the plan — Check the suggested folder names and the files assigned to them. In Agent-2, the analysis view also shows Action, Confidence, and selected-file details.
5. Organize the files — Execute the reviewed plan to move files into the proposed structure.
6. Review or undo — Use Action History to inspect past activity, or Undo Last Run where available to reverse the latest organization run.
🖥️ Application screens
Agent-2 — dashboard and analysis workflow
The dashboard gives you a quick view of the workspace: the current target folder, discovered files, total size, and past organizations. Use Change Folder to choose a different workspace, or Start Organization Workflow to begin.

Agent-2 — Workspace Overview dashboard.

The Organize Workflow screen presents the staged process: Select → Analyze → Review Plan → Organize. After choosing a target folder, use Analyze Files to generate the proposed structure. The table provides Action and Confidence columns, while the File Details panel is ready to show information about a selected file.

Agent-2 — Organize Workflow and analysis view.
Agent-1 — guided organization and plan preview
The earlier Agent-1 interface keeps the main organization controls in the left panel. It includes target-folder selection, naming-engine selection, Preview Organization, Execute & Move, Undo Last Run, Precautions & Rules, and Create Desktop Shortcut.

Agent-1 — guided workflow controls.

Before execution, Preview Organization displays the proposed destination folders and the files assigned to each one. The preview headline summarizes how many files will be organized and how many folders will be created. For example, the supplied screenshot shows a plan for 96 files across 43 folders; this is an example from that screenshot, not a fixed application limit.

Agent-1 — preview plan. Review the proposed structure before choosing Execute & Move.
💻 Requirements
- Windows is the primary platform represented by the supplied application screens.
- Python 3.10 or newer.
- CustomTkinter for the desktop interface.
- Internet access and a configured Gemini integration when using Gemini AI.
The Fast Smart engine uses the Windows Zone.Identifier alternate data stream for download-origin clues. That specific source of metadata is Windows-specific.
🚀 Installation and launch
1. Clone the repository
Replace YOUR_GITHUB_USERNAME with the GitHub account or organization that owns the repository.
git clone https://github.com/YOUR_GITHUB_USERNAME/aegis_agent.git
cd aegis_agent
2. Create and activate a virtual environment
On Windows PowerShell:
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
If PowerShell blocks script activation, you can activate the environment from Command Prompt instead:
.venv\Scripts\activate.bat
3. Install project dependencies
If the repository includes requirements.txt, install the dependencies with:
python -m pip install --upgrade pip
pip install -r requirements.txt
If requirements.txt is not present, install the dependencies listed by the project before launching the application. The supplied README and screenshots do not identify the complete dependency list, so this guide does not guess package versions.
4. Configure Gemini AI (when using that engine)
Fast Smart is the local option. Gemini AI is the online option and requires the Gemini integration to be configured. Follow the configuration method implemented in the project. Do not commit API keys, credentials, or .env files to GitHub.
5. Launch Aegis
Run the Python entry-point file used by your project from the repository folder. For example, if the entry-point file is named main.py:
python main.py
Replace main.py with the actual entry-point filename if your project uses a different one.
🛡️ Safety and privacy
- Review before execution: Check the proposed folder structure before running the organization step.
- No automated deletion: The original project description states that Aegis does not automatically delete files during organization.
- Metadata preservation: The project description specifies preservation of file creation and modification timestamps.
- Undo: The application includes an undo/history mechanism for organization runs. Keep a separate backup of important files; undo should not be treated as a backup strategy.
- Gemini AI is online: Content analyzed through the Gemini engine may be processed by Google's service. Do not use the online engine for confidential or restricted files unless that use is permitted by your privacy, workplace, or client policies.
- Protect credentials: Keep API keys and other secrets out of source control. Use a local environment/configuration method and provide a safe example configuration file if needed.
🧰 Troubleshooting
Issue	What to check
python or py is not recognized	Install Python 3.10+ and enable the option to add Python to PATH. Reopen the terminal after installation.
Dependency installation fails	Confirm that the virtual environment is active and that the repository's requirements.txt is current.
Gemini AI is unavailable	Check internet access and confirm that Gemini credentials/configuration are set up as expected by the project. Fast Smart is the local alternative.
Download-origin grouping is unavailable	The Zone.Identifier metadata used by Fast Smart is Windows-specific and may not exist for every file.
The wrong folder is selected	Recheck the target folder shown in the dashboard or workflow before analyzing or executing.


📌 Project notes
- The application title in the Agent-2 screenshots shows Aegis — Intelligent File Architecture v1.3.0.
- The screenshot examples contain sample folder and file names from one workspace. Your results will depend on the files in the folder you select and the naming engine you use.
- Keep this README's launch command, dependency instructions, and Gemini setup aligned with the actual source code as the project evolves.
<p align="center">
  <strong>Aegis — organize with context, review with confidence.</strong>
</p>