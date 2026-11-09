# Aegis 2.0 — logic review and improvement roadmap

## Improvements implemented

| Previous issue | Change |
| --- | --- |
| Disconnected screens obscured the workflow | Unified folder → preview → result workspace, with separate Recovery and Preferences |
| Users could not omit selected files | Per-file and bulk include/exclude; only included eligible rows execute |
| Destination collisions appeared only when moving | Preflight conflicts shown and excluded from the move count; execution rechecks |
| Manual corrections applied to one file at a time | Multi-selection and bulk destination assignment |
| Heuristic percentages looked more precise than the evidence | Plain Ready / Review name / Conflict labels and an explicit reason |
| Closely spaced downloads could join a session indefinitely | One-hour / 100-file session caps and distinct names for repeated sessions |
| Only one classification style | Session, extension category, and modification-month strategies |
| Background tasks had no cancellation | Cooperative cancellation within hashes and between file operations, with recovery kept |
| Large previews could overwhelm the UI | Bounded pages, debounced search, streaming hashes, and coalesced progress |
| Results disappeared after a run | Retained statuses and safe CSV export, including reasons for skipped files |
| Earlier recovery journals were inaccessible | Recovery screen lists current and archived sessions |
| Empty/excluded executions could replace a recovery journal | No-op operations leave recovery intact |
| UI scaling could make the window taller than the display | Initial geometry accounts for Windows scaling |
| UI and file intelligence were coupled | Separate UI, read-only analysis, and persistence/move modules |

## Recommended next work, in priority order

1. **Custom rule builder and saved presets.** Let users define conditions such as extension, filename pattern, date range, or size, with an explicit order and a preview of matching files. This offers predictable, reusable organization without network calls. Validate conflicting rules and keep manual approval as the default.
2. **Content preview in the inspector.** Add bounded text and image previews, then optional PDF thumbnails. Do not execute or automatically launch unknown files. Decode large or malformed content in an isolated process with size/time limits.
3. **Stronger recovery verification.** Optionally record content hashes for critical files so undo can detect changes that preserve size and timestamps. Persist successful restoration markers for clearer recovery progress. Hashing every file costs I/O, so expose the tradeoff.
4. **Signed installer and upgrade flow.** Produce a signed per-user installer with uninstall registration and version-aware updates. Signing needs an owner-provided certificate. Test upgrades and clean installation on Windows 10/11 and ARM64 before expanding platform claims.
5. **Saved and resumable plans.** Store a plan with source identities, selected rules, and target identity; revalidate everything on resume. Never assume paths still point to the same files after reboot, external edits, or drive reconnection.
6. **Opt-in folder monitoring.** Notify when files settle after a download and propose a new preview. Do not automatically move files until a user explicitly enables and scopes that behavior. Avoid OneDrive placeholders and actively written files.
7. **Accessibility and internationalization.** Validate keyboard focus order and screen-reader labels with assistive technologies; add high-contrast treatment and translations. CustomTkinter has accessibility limitations worth evaluating before deeper enterprise use.

## Deliberate limits and remaining risks

- Scanning is top-level only. Recursive organization needs explicit policies for preserving hierarchy and avoiding cycles/junctions.
- Name/type/time grouping cannot reliably infer document meaning; review remains essential. Gemini only sees names and origins.
- Hashing same-size large files can be slow. Cancellation is checked between blocks, but a blocked filesystem read or network share can still delay it.
- Recovery is identity-based, not a backup. Hard power loss, disk failure, externally edited journals, or changing directory junctions can still require manual recovery. Filesystem path checks are not a security boundary against a concurrent malicious local process.
- Archived sessions are listed newest first; restore newer sessions first if the same files were organized repeatedly. The interface displays up to 100 recovery sessions and 30 recent activity records per folder.
- Cancellation can leave an empty journal/folder if it arrives just before a rename. This is harmless; completed moves retain their recovery paths.
- The packaged app allows one instance per Windows session. Separate source processes or other Windows sessions are not coordinated by a per-folder lock; adding folder-level locking is advisable for shared-drive use.
- Live Gemini requests, clean-machine installation, screen-reader behavior, and very large network folders were not verified in this environment.

## Verification for this release

Automated regression tests cover file collisions, timestamp preservation, file changes since preview, interrupted journals, retryable undo, archived recovery, exclusion/no-op behavior, cancellation, deterministic plans, session bounds, duplicate false positives, month/type grouping, and path validation.

The packaged smoke check exercises startup, all screens, light/dark appearance, analysis, duplicate filtering, inclusion toggles, destination edits, CSV export, actual file moves and undo, Unicode paths, file-type mode, and a 601-row paginated preview using disposable files. Native-window inspection was used to examine the workspace and Preferences and correct display-scaling and contrast issues.
