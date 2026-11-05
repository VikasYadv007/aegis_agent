# Aegis – Intelligent File Architecture Agent

Aegis is a Windows desktop application that helps organize cluttered folders. It analyzes files, suggests a clear folder structure, and lets you review the plan before organizing.

## Features

- **Fast Smart:** Uses local rules to group and organize files.
- **Gemini AI:** Uses Google Gemini for context-aware file analysis.
- **Preview:** Review the suggested folders and file locations before applying changes.
- **Dashboard:** View the selected folder, file count, and total file size.
- **History & Undo:** Review previous organization activity and undo the latest run.
- **Safety-focused:** Includes safeguards for organizing files and keeping a record of changes.

## Requirements

- Windows 10 or 11
- Python 3.10 or newer
- Git
- Internet connection for Gemini AI

## Setup and Run (Windows)

### 1. Install Python

Download Python from [python.org/downloads](https://www.python.org/downloads/). Install Python 3.10 or newer and select **Add Python to PATH** during installation.

Open Command Prompt or PowerShell and verify the installation:

```bash
py --version
```

### 2. Download the project

Open a terminal and run:

```bash
git clone https://github.com/YOUR_USERNAME/aegis_agent.git
cd aegis_agent
```

Replace `YOUR_USERNAME` with the GitHub account that hosts the repository.

### 3. Create and activate a virtual environment

```bash
py -m venv .venv
.\.venv\Scripts\activate
```

### 4. Install the required packages

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 5. Configure Gemini AI (optional)

Fast Smart can be used without a Gemini API key. To use Gemini AI, obtain an API key from [Google AI Studio](https://aistudio.google.com/app/apikey) and add it using the configuration method provided by the project. **Do not share your API key or upload it to GitHub.**

### 6. Start Aegis

Run the application's main Python file from the project folder. For example:

```bash
python main.py
```

If the startup file has a different name, use that file instead of `main.py`.

## Using Aegis

1. Select the folder you want to organize.
2. Choose **Fast Smart** or **Gemini AI**.
3. Analyze the files and review the proposed structure.
4. Select **Execute** to organize the files.
5. Use **Action History** to review activity or **Undo** to revert the latest run.

---

**Note:** The repository should include a `requirements.txt` file listing its Python dependencies. The launch command should match the application's actual entry-point file.
