#!/usr/bin/env bash
# Life Agent 数据备份脚本：MySQL 逻辑备份 + Redis RDB 备份，按日期保留。
#
# 用法（在部署服务器上，配置可通过环境变量覆盖）：
#   BACKUP_DIR=/data/backups RETAIN_DAYS=14 bash deploy/backup.sh
# 建议加入 crontab，每天凌晨 3 点执行：
#   0 3 * * * cd /root/www/lifeagent && set -a && . backend/.env && set +a \
#     && bash deploy/backup.sh >> /var/log/lifeagent_backup.log 2>&1
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/root/backups/lifeagent}"
RETAIN_DAYS="${RETAIN_DAYS:-7}"
MYSQL_HOST="${MYSQL_HOST:-127.0.0.1}"
MYSQL_PORT="${MYSQL_PORT:-3306}"
MYSQL_USER="${MYSQL_USER:-root}"
MYSQL_PASSWORD="${MYSQL_PASSWORD:-}"
MYSQL_DB="${MYSQL_DB:-lifeagent}"
REDIS_CONTAINER="${REDIS_CONTAINER:-life-redis}"

STAMP="$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

# 1) MySQL 逻辑备份（--single-transaction 不锁表；空密码时不带 -p）
if command -v mysqldump >/dev/null 2>&1; then
  if [ -n "$MYSQL_PASSWORD" ]; then
    mysqldump -h"$MYSQL_HOST" -P"$MYSQL_PORT" -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" \
      --single-transaction --routines --events "$MYSQL_DB" \
      | gzip > "$BACKUP_DIR/mysql_${MYSQL_DB}_${STAMP}.sql.gz"
  else
    mysqldump -h"$MYSQL_HOST" -P"$MYSQL_PORT" -u"$MYSQL_USER" \
      --single-transaction --routines --events "$MYSQL_DB" \
      | gzip > "$BACKUP_DIR/mysql_${MYSQL_DB}_${STAMP}.sql.gz"
  fi
  echo "mysql backup done: $BACKUP_DIR/mysql_${MYSQL_DB}_${STAMP}.sql.gz"
else
  echo "mysqldump not found on host, skip mysql backup" >&2
fi

# 2) Redis RDB 备份：容器内 BGSAVE，再把 dump.rdb 复制出来压缩
if docker ps --format '{{.Names}}' | grep -q "^${REDIS_CONTAINER}$"; then
  docker exec "$REDIS_CONTAINER" redis-cli BGSAVE >/dev/null || true
  sleep 5
  docker cp "$REDIS_CONTAINER":/data/dump.rdb "$BACKUP_DIR/redis_${STAMP}.rdb"
  gzip -f "$BACKUP_DIR/redis_${STAMP}.rdb"
  echo "redis backup done: $BACKUP_DIR/redis_${STAMP}.rdb.gz"
else
  echo "redis container '$REDIS_CONTAINER' not running, skip redis backup" >&2
fi

# 3) 清理超过保留期的备份
find "$BACKUP_DIR" -type f -name '*.gz' -mtime +"$RETAIN_DAYS" -delete
echo "backup finished: dir=$BACKUP_DIR stamp=$STAMP retain_days=$RETAIN_DAYS"
