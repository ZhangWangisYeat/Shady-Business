@AGENTS.md

# Claude Code
Use `AGENTS.md` as the shared source of truth alongside Codex. Claude-only notes: avoid reading the entire `docs/` tree; load the relevant skill and contract for each task. The app uses a native Expo **development build**, not Expo Go. Do not introduce a web frontend by default.

## Running the app (Claude Code)
When asked to run, start or test the app, follow **"Run and smoke-test the app locally"** in `AGENTS.md` step by step:
- **Long-running processes:** start the emulator, uvicorn and Metro with `run_in_background`. Use an `until …; do sleep 1; done` check (boot_completed, `/api/health`, Metro `/status`) instead of plain sleeps.
- **Native build:** run `expo run:android` in the background with output redirected to a log in the scratchpad. Watch it with a Monitor that greps `BUILD SUCCESSFUL|BUILD FAILED|What went wrong|401`.
- **Screenshots:** save `adb exec-out screencap -p` captures to the scratchpad and look at them with the Read tool. Images are shown scaled, so map coordinates back to 1080×2400 before tapping.
- **Shell:** use the Bash tool for adb/emulator commands (Git Bash). Use PowerShell only for user env vars and killing stray `node.exe`.
- **Permissions:** the user has to approve SDK license acceptance and the Windows Firewall prompt themselves. The Mapbox `pk.` token comes from the user and is never generated or committed.
