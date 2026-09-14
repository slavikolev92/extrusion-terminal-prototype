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

Task 25 backup/delivery installation is intentionally separate from this app
deployment. Deploying source does not install or enable its timers. Use
`docs/production-artifact-delivery.md` only during a separately authorized
infrastructure operation.

## Normal Deploy

SSH or open a terminal on the production VM and run:

```bash
cd /opt/extrusion-terminal/app
bash scripts/deploy_production.sh
```

The script may ask for the sudo password when it restarts `extrusion-terminal.service`. That is expected in the current production setup. The password prompt is the human checkpoint before production is restarted.

All deployment Git revision, status, fetch, and fast-forward operations suppress
replacement objects and clear repository/object/config selection overrides.
This prevents a local replace ref from falsifying the exact GitHub revision
attestation while preserving the normal SSH/authentication environment needed
for `fetch`.

The script always requires the root-protected
`/opt/extrusion-terminal/maintenance.lock` created by the Task 25 installer and
holds it before inspecting Task 25 installation state. If Task 25 is installed,
it also takes `/opt/extrusion-terminal/artifact-delivery/operation.lock`
exclusively, records which Task 25 timers were enabled, and disables both before
the pre-activation backup. Only after code activation, verification, restart,
and final health checks does it restore the previously enabled timers. A failed
deployment leaves both disabled so they cannot import an unverified checkout.

## What The Script Does

The deploy script:

1. Verifies it is in the production checkout.
2. Requires and exclusively acquires the protected maintenance lock before
   inspecting the four Task 25 units.
3. Verifies the expected branch and refuses a dirty working tree.
4. If all four Task 25 units exist, requires the existing operation lock,
   acquires it exclusively, records enabled timers, and disables both. A
   partial or unsafe unit installation is a refusal.
5. Fetches GitHub explicitly with a branch refspec while both relevant locks
   are held:

   ```bash
   git fetch --prune origin +refs/heads/main:refs/remotes/origin/main
   ```

6. Creates a SQLite-safe backup before activating new code.
7. Fast-forwards the local `main` branch to `origin/main`.
8. Installs runtime dependencies from `requirements.txt`.
9. Runs Python syntax/import checks.
10. Runs pytest if it is installed in the production virtualenv.
11. Writes `.deploy/current_revision` with the exact Git commit being deployed.
12. Restarts `extrusion-terminal.service`.
13. Verifies:
    - systemd reports the service active
    - the service PID changed after restart
    - the process working directory is `/opt/extrusion-terminal/app`
    - the process command is the expected uvicorn command
    - port `8000` is owned by the service PID
    - `/health` responds with `status: ok`
    - `/health` reports the exact deployed Git revision
    - the checkout still matches the fetched GitHub commit
    - all four installed Task 25 units still byte-match the deployed checkout
      and pass `systemd-analyze verify`
14. Restores only the Task 25 timers that were enabled before deployment and
    confirms each restored timer is both enabled and active.

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
- **Maintenance anchor/lock missing or unsafe:** run the accepted Task 25
  installer procedure; do not let deployment create or weaken infrastructure.
- **Incomplete Task 25 installation:** all four units must be present, regular,
  root-owned mode-`644` files or all four must be absent.
- **Task 25 operation lock missing/unsafe:** repair the incomplete installation
  through the installer; deployment never creates runtime state.
- **Task 25 lock timeout:** a scheduled job did not release the shared lock
  within the bounded deployment wait. Inspect both Task 25 service journals.
- **Task 25 unit mismatch:** the deployed revision changed a tracked unit, or
  installed unit bytes drifted. The failed deploy deliberately leaves both
  timers disabled. Run the accepted-revision installer procedure from
  `docs/production-artifact-delivery.md`, repeat its required acceptance if the
  unit behavior changed, and re-enable only after successful verification.
- **Task 25 timer resume failure:** systemd accepted the enable command but a
  previously enabled timer did not remain enabled and active. The failure trap
  disables both timers; inspect the unit journal and complete a successful
  deployment before re-enabling.
- **Health revision mismatch:** the restarted app did not report the exact commit that was deployed.

If a refusal/failure occurs after Task 25 timers were stopped, the script states
that they remain disabled. Do not re-enable them against the failed checkout.
Correct the deployment problem and complete one successful deployment first.

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
