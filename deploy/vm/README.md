# Auto-deploy to the VM

Flow: merge to `main` -> GitHub Actions runs tests/build -> if green, publishes a bundle to the `deploy` branch
-> a timer on the VM checks every 5 minutes and deploys it when it is safe.
No secrets anywhere, and GitHub never connects to the VM.

## Install (once, from your Mac Terminal)

    gcloud compute ssh --zone "asia-south1-a" "fyers-algo" --project "fyers-510017" \
      --command 'curl -fsSL https://raw.githubusercontent.com/mani124/BB/deploy/deploy/vm/install.sh | sudo bash'

(The `deploy` branch exists after the first green run on `main`.) Then check `sudo bb-deploy --dry-run`.

## What a deploy does
Deploys only when ALL hold: the bundle is newer than what runs, it was built by CI after green tests, it is outside
09:15-15:30 IST, no position is OPEN/TARGET_1 in trades.db (unreadable db = no deploy), no `PAUSE` file, and
(optional) the commit is approved.
Restarting between sessions is safe; positions persist in trades.db and are managed again after the restart.
Then: backup to `/home/mani_vutla7/bb-backups/deploy-<time>/` (code, built frontend, consistent trades.db copy; last 10 kept),
replace `backend/app` and `frontend/dist`, `pip install` only if `requirements.txt` changed, restart ONLY `bb-options.service`,
wait for `/api/health` and an active service, and roll back automatically on failure (that commit is then not retried).
`.env`, `trades.db`, the venv, caddy, fyers-web and fyers-daemon are never touched. Everything is logged to `/var/log/bb-deploy.log`.

## Controls
- Pause: `sudo touch /etc/bb-deploy/PAUSE` / resume: `sudo rm /etc/bb-deploy/PAUSE`
- Manual approval: set `REQUIRE_APPROVAL=1` in `/etc/bb-deploy/config`, then approve each build with `sudo bb-deploy-approve <commit>`
- Remove: `curl -fsSL https://raw.githubusercontent.com/mani124/BB/deploy/deploy/vm/uninstall.sh | sudo bash`

## Limits
- A rollback does not undo `pip install` changes or database schema changes made by a new version.
- Anyone who can push to `main` controls what goes live. Consider branch protection.
- `FRONTEND_DIST` defaults to `<app>/frontend/dist`; if caddy serves the site from elsewhere, set it in the config file.

## Morning readiness alerts
The app checks itself and sends a Telegram message (needs `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`) at 09:00 IST on trading days listing anything not OK: Dhan login, feed, backup age (reads `/var/lib/bb-backup`), failed deploy (reads `/var/lib/bb-deploy/failed`), disk use (warn 80%, fail 90%), NSE holiday list, Telegram, live-routing session and kill switch. If Dhan is still not logged in it reminds at 09:10 and 09:20, and at 18:00 it alerts on machine problems (backup, disk, holiday list). Same data: `GET /api/readiness`. Override the state directories with `BB_BACKUP_STATE_DIR` / `BB_DEPLOY_STATE_DIR`. The app user must be able to read those directories.

## Clean restarts (graceful shutdown)
The dashboard's live stream (`/api/signals/stream`) stays open while a browser tab is open, and uvicorn waits for open connections on SIGTERM, so a restart could hang until systemd sent SIGKILL (seen at 15:35 on 2026-10-16). Make uvicorn cancel leftover connections after a few seconds: add `--timeout-graceful-shutdown 10` to the `ExecStart` line of `bb-options.service` (or set `UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN=10` in the service's environment file), then `sudo systemctl daemon-reload && sudo systemctl restart bb-options` outside market hours. Cancelling does not skip the save: the app still flushes pending trade writes in its shutdown step. Check with `journalctl -u bb-options -n 30` after a restart: you should see "Application shutdown complete" and no SIGKILL.
