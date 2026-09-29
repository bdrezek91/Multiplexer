# Backup Multipleksera

Backup obejmuje:
- PostgreSQL (pg_dump --format=custom),
- dokumenty z MinIO eksportowane logicznie przez API S3,
- manifest SHA-256,
- LAST_SUCCESS używany przez healthcheck.

Domyślna lokalizacja: /var/backups/multiplekser.
Domyślna retencja: 14 dni.

Ręczny backup:
sudo /root/Multiplexer/multiplekser/ops/backup.sh
sudo /root/Multiplexer/multiplekser/ops/check-backup.sh

Systemd:
- /etc/systemd/system/multiplekser-backup.service
- /etc/systemd/system/multiplekser-backup.timer

Timer uruchamia backup codziennie około 03:30 UTC z losowym opóźnieniem do 10 minut.

Ważne: to jest kopia lokalna na tym samym VPS. Chroni przed błędem aplikacji lub przypadkową
utratą danych, ale nie przed utratą całego serwera/dysku. Kolejnym etapem powinien być drugi
backup off-site. Sekrety z .env nie są kopiowane do tego backupu.
