# Nightly trades.db backup (Google Cloud Storage)

Every night at 04:00 IST (22:30 UTC, market closed) a systemd timer runs `bb-backup`:
SQLite online backup of `trades.db` to a temp file in `/var/tmp` (consistent while the app runs, integrity-checked),
gzip, upload to `gs://<bucket>/trades/trades-<UTC time>.db.gz`, delete the temp file. Needs ~size of the db in free space
(refuses to run with under 50 MB free). No keys: it uses the VM's service account, which must have write access to the bucket only.

## Bucket
Private, uniform bucket-level access, public access prevented, region asia-south1. A lifecycle rule deletes objects older than
30 days (`lifecycle.json`). Grant the VM service account `roles/storage.objectUser` on this bucket only (not project-wide).

## Check / run
    bb-backup --status          # exit 1 if last run failed or no success in 36h
    sudo bb-backup              # run now
    systemctl list-timers bb-backup.timer ; tail /var/log/bb-backup.log
A failed run leaves `/var/lib/bb-backup/last_failure`, shows `bb-backup.service` as failed in `systemctl --failed`, and is logged.

## Restore
    gcloud storage ls gs://<bucket>/trades/
    gcloud storage cp gs://<bucket>/trades/trades-<time>.db.gz /var/tmp/ && gunzip /var/tmp/trades-<time>.db.gz
    sqlite3 /var/tmp/trades-<time>.db 'PRAGMA integrity_check; select count(*) from positions;'   # python3 sqlite3 also works
Then stop `bb-options.service`, keep the current db as `trades.db.bad`, copy the restored file to
`backend/data/trades.db` (owner mani_vutla7), start the service. Restore only outside 09:15-15:30 IST.

## Install (on the VM)
    sudo BUCKET=<bucket> bash install-backup.sh     # from a checkout of deploy/vm
Remove: `sudo systemctl disable --now bb-backup.timer; sudo rm /usr/local/bin/bb-backup /etc/systemd/system/bb-backup.* ; sudo rm -r /etc/bb-backup`
