# Production Deploy Script Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a repeatable production deployment command that fetches the latest GitHub `main`, backs up data, restarts the service, and proves the live process is running the deployed commit.

**Architecture:** A Bash script owns the production update procedure and uses explicit checks around Git, SQLite backup, systemd, process identity, port ownership, and `/health`. The FastAPI health response remains backwards-compatible and adds deployment metadata read from a script-written revision file.

**Tech Stack:** Bash, Git, systemd, FastAPI, SQLite-safe `app.backups`, pytest.

---

### Task 1: Deployment Metadata

**Files:**
- Create: `app/deployment.py`
- Modify: `app/main.py`
- Test: `tests/test_baseline.py`

- [ ] Add a helper that reads `.deploy/current_revision` from the app root and returns `{"app_revision": value}` when present, otherwise `{"app_revision": None}`.
- [ ] Include that metadata in `/health` without removing existing keys.
- [ ] Add a focused test that writes a temporary revision file, calls the helper, and verifies whitespace is stripped.

### Task 2: Production Deploy Script

**Files:**
- Create: `scripts/deploy_production.sh`

- [ ] Add a strict Bash script with production defaults from the fact dump.
- [ ] Support `--dry-run`, `--skip-tests`, and config overrides for app dir, service, remote, branch, health URL, port, database path, and backup dir.
- [ ] Refuse dirty local Git state by default.
- [ ] Fetch `origin/main`, fast-forward only, back up the production SQLite DB, install dependencies, run checks, restart systemd with manual sudo, and verify the live service.
- [ ] Write `.deploy/current_revision` before restart and verify `/health` reports that exact revision after restart.

### Task 3: Operator Documentation

**Files:**
- Create: `docs/production-deployment.md`
- Modify: `README.md`

- [ ] Document the normal deployment command, what success proves, what it refuses to do, and how to handle sudo.
- [ ] Link the new production deployment procedure from the operational section in `README.md`.

### Task 4: Verification

**Files:**
- No additional file changes.

- [ ] Run Bash syntax checks on the deploy script.
- [ ] Run focused tests for deployment metadata and health behavior.
- [ ] Run the full Python test suite.
- [ ] Run `git diff --check`.
