# Deployment Quick Reference

Use this when updating the production VM to the latest GitHub code.

## Production App

- VM/app host: `extrusion-app`
- app directory: `/opt/extrusion-terminal/app`
- service: `extrusion-terminal.service`
- production database: `/opt/extrusion-terminal/data/extrusion_terminal.sqlite3`
- backup directory: `/opt/extrusion-terminal/backups`
- local health check: `http://127.0.0.1:8000/health`

## Normal Deployment Command

Run this on the production VM:

```bash
cd /opt/extrusion-terminal/app
bash scripts/deploy_production.sh
```

Enter the `sudo` password when the script asks for it. The password prompt happens when the script restarts `extrusion-terminal.service`.

## What Success Looks Like

The script should finish with:

```text
DEPLOYMENT OK
```

The output should also show:

- a SQLite-safe backup was created under `/opt/extrusion-terminal/backups`
- the service restarted with a new PID
- port `8000` is owned by the new service PID
- `/health` returned `"status":"ok"`
- `/health` returned `"app_revision"` equal to the deployed Git commit

Example success line:

```text
deployed_commit=f6123c8669c1b0ab11698ba5ecf7ee8e4f7ce32d
```

## If The Script Fails

Do not manually restart or edit files to bypass the failure.

First check the deploy log printed by the script, for example:

```text
/opt/extrusion-terminal/app/.deploy/logs/deploy_YYYYMMDDTHHMMSSZ.log
```

Common causes:

- local production checkout has uncommitted or untracked files
- GitHub cannot be fetched
- SQLite backup failed
- the service failed to restart
- `/health` did not report the deployed revision

## First-Time Bootstrap

This was only needed before the deploy script existed on the production VM:

```bash
cd /opt/extrusion-terminal/app
git fetch --prune origin +refs/heads/main:refs/remotes/origin/main
git merge --ff-only origin/main
bash scripts/deploy_production.sh
```

After the script exists on the VM, use the normal deployment command only.

## Detailed Procedure

See [production-deployment.md](production-deployment.md) for the full production deployment procedure and failure handling notes.
