# Production Deployment Procedure

This procedure updates the extrusion terminal VM to the latest GitHub `main` and proves the live service is running that exact revision.

Production defaults confirmed on 2026-07-17:

- app checkout: `/opt/extrusion-terminal/app`
- systemd service: `extrusion-terminal.service`
- service user: `sk`
- database: `/opt/extrusion-terminal/data/extrusion_terminal.sqlite3`
- backups: `/opt/extrusion-terminal/backups`
- app URL: `http://APP-VM-IP:8000/`
- local health check: `http://127.0.0.1:8000/health`

## Normal Deploy

SSH or open a terminal on the production VM and run:

```bash
cd /opt/extrusion-terminal/app
bash scripts/deploy_production.sh
```

The script may ask for the sudo password when it restarts `extrusion-terminal.service`. That is expected in the current production setup. The password prompt is the human checkpoint before production is restarted.

## What The Script Does

The deploy script:

1. Verifies it is in the production checkout.
2. Refuses to continue if the Git working tree has local changes or untracked files.
3. Fetches GitHub explicitly with a branch refspec:

   ```bash
   git fetch --prune origin +refs/heads/main:refs/remotes/origin/main
   ```

4. Creates a SQLite-safe backup before activating new code.
5. Fast-forwards the local `main` branch to `origin/main`.
6. Installs runtime dependencies from `requirements.txt`.
7. Runs Python syntax/import checks.
8. Runs pytest if it is installed in the production virtualenv.
9. Writes `.deploy/current_revision` with the exact Git commit being deployed.
10. Restarts `extrusion-terminal.service`.
11. Verifies:
    - systemd reports the service active
    - the service PID changed after restart
    - the process working directory is `/opt/extrusion-terminal/app`
    - the process command is the expected uvicorn command
    - port `8000` is owned by the service PID
    - `/health` responds with `status: ok`
    - `/health` reports the exact deployed Git revision
    - the checkout still matches the fetched GitHub commit

If all checks pass, the script prints `DEPLOYMENT OK`.

## Dry Run

To verify paths and service visibility without changing code, backing up, installing dependencies, or restarting:

```bash
cd /opt/extrusion-terminal/app
bash scripts/deploy_production.sh --dry-run
```

## Test Options

By default, the script runs pytest only if pytest is installed in the production virtualenv. This avoids blocking deployment on missing dev-only dependencies.

Require pytest:

```bash
bash scripts/deploy_production.sh --require-tests
```

Skip pytest:

```bash
bash scripts/deploy_production.sh --skip-tests
```

The script always runs Python syntax/import checks.

## If The Script Refuses To Deploy

Do not bypass the refusal by manually restarting services.

Common refusal cases:

- **Dirty working tree:** production has local files or edits not represented in GitHub. Review with `git status --short`.
- **Wrong branch:** production is not on `main`.
- **Diverged branch:** production has local commits that cannot fast-forward to GitHub `main`.
- **Backup failure:** the production SQLite database could not be backed up safely.
- **Health revision mismatch:** the restarted app did not report the exact commit that was deployed.

When a refusal happens, preserve the deploy log from:

```text
/opt/extrusion-terminal/app/.deploy/logs/
```

Then inspect the refusal before attempting another deployment.

## Manual Verification After Deploy

Open these from a trusted LAN or Tailscale client:

- `http://APP-VM-IP:8000/admin`
- `http://APP-VM-IP:8000/terminal`

From the VM, the local health endpoint should show the deployed revision:

```bash
curl --fail --silent --show-error http://127.0.0.1:8000/health
```

The JSON should include:

```json
{
  "status": "ok",
  "app_revision": "the deployed Git commit"
}
```
