#!/bin/bash
DIR="/home/dfzz/backups/mysql"
MYSQLDUMP="/home/dfzz/anaconda3/bin/mysqldump"
SOCK="/tmp/mysql.sock"
mkdir -p "$DIR"
DATE=$(date +%Y%m%d)
FILE="$DIR/wx_miniapp_${DATE}.sql.gz"
"$MYSQLDUMP" -S "$SOCK" -u miniapp -pMiniApp@2024! --single-transaction --routines --triggers wx_miniapp | gzip > "$FILE"
echo "Backup: $(du -h "$FILE" | cut -f1) -> $FILE"
find "$DIR" -name "*.sql.gz" -mtime +7 -delete
ls -lh "$DIR"
