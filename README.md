# Aegis 2.0 — Windows File Organizer

Open `dist\Aegis\Aegis.exe`, or use the existing **Aegis File Organizer** Desktop / Start-menu shortcut. The portable distribution is `dist\Aegis-Windows-x64.zip`. Extract it before launching. Python is not needed on the destination computer. Keep `Aegis.exe` and `_internal` together.

To create shortcuts on another computer, run `Install-Shortcuts.cmd` inside the extracted Aegis folder. No administrator installation is needed. Move the folder to its permanent location before making shortcuts. This is a Windows 10/11 x64 build, verified on the current Windows 11 computer. The executable is unsigned because no signing certificate was supplied.

## What's new

- Rebuilt workspace with a navy sidebar, clear hierarchy, light/dark/system appearance, branded icon, and Windows DPI-aware initial sizing.
- Folder choice, analysis, review, and execution in one workspace; recent-folder shortcuts.
- Search, sortable columns, attention/duplicate/excluded filters, multi-selection, include/exclude toggles, and bulk destination edits.
- 250-row pages keep large previews manageable; progress updates are coalesced so file processing cannot flood the UI event queue.
- Smart sessions, file-type folders, last-modified-month folders, and optional Gemini-assisted naming.
- Conflict detection during preview, explicit reasons in the inspector, persistent run results, and UTF-8 CSV reports.
- Cancellation during analysis, hashing, moves, and recovery; completed partial moves remain recoverable.
- Recovery for current and archived sessions, plus activity records that distinguish organizing from restoring.

## Everyday workflow

1. Choose a folder. Aegis scans its immediate files, not its subfolders.
2. Choose an organizing mode and click **Analyze folder**. Nothing moves during analysis.
3. Search or filter the preview. Select files to inspect their reasons and edit destinations. Ctrl-click / Shift-click selects several rows. Use the **Use** column or Space to include/exclude selected files. Include/exclude page affects only the displayed page.
4. **Organize N files** confirms and applies the included preview. Existing destination files are never overwritten. The result stays visible and can be exported.
5. Use **Undo latest** or **Recovery** to restore a session. Restore newer sessions first when they involve the same files. Resolve conflicts and retry the retained session if necessary.

Keyboard shortcuts: **Ctrl+O** choose folder; **Ctrl+F** search; **Ctrl+Enter** organize reviewed files; **Escape** request cancellation. Cancellation stops after the current file or bounded network request; it does not reverse completed moves automatically.

## Modes and privacy

**Smart sessions** uses timestamps, filename keywords, and website origins when present in Windows download metadata. Sessions are limited to an hour and 100 files. Name suggestions marked “Review name” deserve your attention; they are heuristic suggestions, not statistically calibrated confidence scores.

**File type** groups into Documents, Images, Spreadsheets, Presentations, Video, Audio, Archives, Installers, Code, or Other files. **By month** uses modification time, not creation time.

**Gemini assisted** requires an API key entered in Preferences for the current session. Only filenames and website origins are sent, after confirmation; document/image contents are not uploaded. Each naming request has a 20-second timeout and one attempt, with offline fallback on failure. Model availability and API charges depend on your Google account. `AEGIS_GEMINI_MODEL` overrides the default model. Live Gemini network requests were not exercised in verification.

Duplicate detection uses file size to narrow candidates, followed by streamed SHA-256 hashing. Duplicates are moved to a review folder, never deleted. Disable this check in Preferences for faster scans of very large files. Exclusions are saved for the next analysis. Partial downloads, symlinks, app state files, and the running executable are excluded automatically.

## Recovery and data

Windows same-volume rename preserves existing file metadata without copy/delete overhead. Before every rename, a recovery intent is flushed to `.aegis-undo.jsonl` inside the selected folder. New sessions archive the preceding journal under `.aegis-history`. Keep these files with the organized directory. Recovery refuses occupied original locations and files whose size, modification time, or identity changed. These checks do not detect deliberate modifications that preserve those values and are not a substitute for backups.

Settings, recent folders, activity, and rotating logs are stored in `%LOCALAPPDATA%\Aegis`. Project-local legacy API keys are not migrated or bundled. Old Agent 1 undo logs must be handled by the original script; 1.4 recovery journals are compatible with the new Recovery screen. `agent-1.py` remains unchanged. `agent-2.py` now forwards to the current application.

## Source and rebuild

- `aegis_app.py`: UI, workflow states, background-task coordination.
- `aegis_analysis.py`: read-only scanning, hashing, grouping, optional AI naming.
- `aegis_core.py`: atomic persistence, no-overwrite moves, recovery journals.
- `main.py`: logging and single-instance Windows launcher.
- `tests/`: planning and recovery regression checks.
- `aegis_smoke.py`: executable integration checks on temporary sample files.

With Windows x64 and Python 3.14:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build.ps1
```

The build installs pinned dependencies, runs the safety/planning tests, packages the executable, verifies its UI workflow on temporary files, and creates the portable ZIP. No user documents are moved during verification. Optional development formatter: Black 26.10.1. Run source with `.\.venv\Scripts\python.exe main.py`.

Read `LOGIC_REVIEW.md` for the logic review, limitations, and proposed next improvements.
