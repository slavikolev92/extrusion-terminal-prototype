# Milestone 8 Prompt - Backup And Recovery

You are continuing work on the extrusion terminal pilot repository at:

`C:\Users\slavi\Dropbox\03 KolevOOD\7 Extrusion Terminal Prototype`

You have express permission to use subagents for tasks that are parallelizable and where they are genuinely useful, such as independent code review, test review, documentation review, or operational-safety review. Do not use subagents to skip reading required project instructions yourself.

If any requirement is ambiguous after reading the required files and inspecting the current code, stop and ask the user instead of guessing.

First, read these files in this order:

1. `AGENTS.md`
2. `README.md`
3. `IMPLEMENTATION_PLAN.md`
4. `IMPLEMENTATION_HANDOFF.md`

Then inspect the current code under:

- `app/`
- `app/templates/`
- `app/static/css/app.css`
- `tests/`

Also read the prior milestone prompt for continuity:

- `prompts/milestone-7-finish-cancel-and-history.md`

Current state:

- Milestones 0 through 7 are complete and committed.
- Latest completed commit should be `3f53dde Add finish cancel and history milestone`.
- Milestone 7 added finish, cancel, and history behavior:
  - finish validation
  - active timing segment closure on finish
  - completed cards leave the active queue and appear in completed/cancelled history
  - cancellation without reason
  - cancellation closes an open running segment with `correction`
  - cancelled cards can be restored to `pending`
  - restore blocks duplicate active machine sequence conflicts
  - completed-card material, tare, and roll corrections remain editable where confirmed
  - tests in `tests/test_finish_cancel_history.py`
- Milestone 7 automated suite ended at `38 passed`.
- Current next milestone in `IMPLEMENTATION_PLAN.md` should be `Milestone 8 - Backup And Recovery`.

Important environment note:

- Git works, but `.git` writes may require escalation/approval.
- Python on this PC may require the temporary working venv at `.test-runtime\codex-venv`.
- The current successful test command is:

```powershell
.\.test-runtime\codex-venv\Scripts\python.exe -m pytest
```

- If needed, verify with:

```powershell
git status --short
git log -1 --oneline
.\.test-runtime\codex-venv\Scripts\python.exe -m compileall app tests
.\.test-runtime\codex-venv\Scripts\python.exe -m pytest
```

- If you need to start the app for manual browser testing, avoid hidden/background PowerShell process creation because antivirus objected to it. Prefer the plain visible terminal approach:

```powershell
cmd /c start "Extrusion Terminal App" .\.test-runtime\codex-venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Then check:

```powershell
Invoke-WebRequest -Uri http://127.0.0.1:8000/health -UseBasicParsing -TimeoutSec 5
```

Implement only Milestone 8 - Backup And Recovery.

Milestone 8 scope:

- Add SQLite-safe backup behavior.
- Create timestamped database backup files.
- Add a simple retention policy.
- Add a documented restore procedure.
- Add a documented startup command.
- Add a documented shutdown/restart procedure.
- Document the database location.
- Document the backup location.
- Add basic troubleshooting notes for:
  - failed imports
  - duplicate releases
  - server restart
- Add focused automated tests for backup and restore behavior.
- Do a focused manual backup/restore check using a temporary database, not the real runtime database.

Explicitly out of scope for Milestone 8:

- Print output.
- User accounts/login/permissions.
- Writing terminal-entered data back to Excel.
- Public internet exposure.
- Detailed machine performance or downtime tracking.
- Complex backup scheduling UI.
- Cloud backups.
- Email/notification alerts.
- Windows Task Scheduler, cron, or systemd timer installation unless the user explicitly asks.
- Mutating or restoring over `data/extrusion_terminal.sqlite3` during automated/manual tests.

Important backup/recovery rules:

- Use SQLite-safe backup behavior. Do not rely on unsafe raw file copying while the app may be writing.
- Prefer Python's `sqlite3.Connection.backup()` API or an equivalent safe SQLite backup mechanism.
- Backups must be timestamped so they do not overwrite each other.
- Backup and restore tests must use temporary SQLite database paths.
- Restore must be documented clearly enough that a future operator/admin can recover from a backup copy before pilot use.
- The implementation should remain simple, inspectable, and repo-local.
- Keep any retention policy simple and predictable.

Recommended implementation approach:

1. Review current runtime path handling in `app/db.py`:
   - `DATA_DIR`
   - `DB_PATH`
   - `connect()`
   - `init_db()`
2. Decide the smallest clean place for backup utilities. Prefer a simple module such as `app/backups.py` unless the existing code suggests a better local pattern.
3. Add backup configuration:
   - default backup directory should be easy to find, for example `backups/` at the repository root.
   - consider an environment variable such as `EXTRUSION_BACKUP_DIR` only if it keeps the code simple and testable.
4. Add a function to create a timestamped SQLite-safe backup:
   - create the backup directory if missing
   - open the source database read-only/safely where practical
   - write to a timestamped `.sqlite3` backup file
   - use SQLite backup API rather than raw copy
   - return the backup path and useful metadata if helpful
5. Add a simple retention function:
   - keep the newest backups
   - remove older backup files only inside the configured backup directory
   - avoid broad or destructive file operations
   - make the retention count explicit and testable
6. Add a restore helper if appropriate:
   - it may restore from a backup path into a specified target database path for tests
   - do not restore over the real runtime database during tests
   - use SQLite-safe copying/backup semantics where possible
   - validate that the backup file exists before restore
7. Add a CLI or script entry point only if it is the simplest way to make backup/restore operational:
   - acceptable shapes include `python -m app.backups backup` or a small script under `scripts/`
   - keep commands documented
   - do not add a background service
8. Add focused tests, probably `tests/test_backup_recovery.py`, for:
   - backup creates a timestamped SQLite file in the configured backup directory
   - backup preserves real database contents by restoring into a separate temp database and querying expected rows
   - backup can run while another SQLite connection to the source database is open
   - restore refuses a missing backup path
   - retention keeps the newest N backup files and removes only older matching backup files in the backup directory
   - backup/restore tests do not mutate `data/extrusion_terminal.sqlite3`
9. Run:

```powershell
.\.test-runtime\codex-venv\Scripts\python.exe -m compileall app tests
.\.test-runtime\codex-venv\Scripts\python.exe -m pytest
git diff --check
```

10. Do a focused manual backup/restore check with a temporary database, not `data/extrusion_terminal.sqlite3`:
    - initialize a temp database
    - import/release or insert a small sample card using existing helpers
    - create a backup
    - restore the backup into a different temp database path
    - query the restored database and verify the sample data exists
    - verify the real runtime database was not touched
11. Update docs:
    - `IMPLEMENTATION_PLAN.md`: mark Milestone 8 done and Milestone 9 next
    - `AGENTS.md`: current milestone state
    - `IMPLEMENTATION_HANDOFF.md`: current state, test count, next milestone notes
    - `README.md`: operational backup/recovery section with:
      - startup command
      - shutdown/restart procedure
      - database location
      - backup location
      - backup command
      - restore procedure
      - troubleshooting notes for failed imports, duplicate releases, and server restart
12. Review changed code for:
    - SQLite-safe backup behavior
    - restore safety
    - retention safety and path boundaries
    - no mutation of the real runtime database during tests
    - clear operator/admin documentation
    - scoped changes only
13. Stage and commit with a milestone-level message such as:

```text
Add backup and recovery milestone
```

Remember:

- Do not mutate the real runtime database during automated or manual checks unless the user explicitly asks for live-app testing.
- Do not restore over `data/extrusion_terminal.sqlite3` during tests.
- Do not leave uncommitted milestone work.
- Do not include the untracked `prompts/` folder in the milestone commit unless the user explicitly asks you to commit prompts too.
- If `.git` writes require escalation, request approval for `git add` and `git commit`.
- Keep Milestone 8 separate from printing.
