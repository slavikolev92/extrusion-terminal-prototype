# Guidance: Download the Latest Production Database

This is operator/agent guidance only. It is not automation, a deployment
procedure, or authorization to access a production host or database.

When the user asks how to download the latest production database, provide only the following workflow.

## 1. Create the backup on the production server

The user is already connected to production over SSH. Give this exact command:

```bash
cd /opt/extrusion-terminal/app && .venv/bin/python -m app.backups backup --source /opt/extrusion-terminal/data/extrusion_terminal.sqlite3 --backup-dir /opt/extrusion-terminal/backups --keep 144
```

Then ask the user to provide the filename printed after `Created backup:`.

## 2. Download that backup to Windows Downloads

After the user provides the filename, replace `<BACKUP_FILENAME>` in both places below and give this command for Windows Command Prompt:

```cmd
scp sk@extrusion-app:/opt/extrusion-terminal/backups/<BACKUP_FILENAME> "%USERPROFILE%\Downloads\<BACKUP_FILENAME>"
```

The `scp` command must be run from Windows Command Prompt, not from inside the production SSH session.

Do not add checksums, diagnostic commands, or alternative procedures unless the user explicitly requests them.
