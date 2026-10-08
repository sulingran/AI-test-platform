#!/usr/bin/env bash
# TestHub 一键部署脚本（Docker Compose）
#
# 用途：在一台已装好 Docker + Docker Compose 的 Linux 服务器上，从源码目录
# 一键构建并拉起 TestHub（mysql / redis / backend / scheduler / frontend）。
#
# 用法：
#   ./deploy-testhub.sh                    # 首次部署（自动生成 .docker_env）
#   ./deploy-testhub.sh --dump /path/to/testhub_db.sql   # 首次部署 + 导入业务库
#   ./deploy-testhub.sh --reset-admin      # 已部署后，把 admin 密码重置为 ITadmin@123
#   ./deploy-testhub.sh --stop             # 停止所有服务（不删数据）
#
# 约定：
#   - 密码统一使用 ITadmin@123（含 MySQL root、应用库账号、admin 登录）。
#   - 脚本永不执行 `docker compose down -v`，停止只用 `stop`，数据卷不会丢。
#   - 幂等：可重复执行；已存在 .docker_env 时不覆盖。
#
# 可通过环境变量覆盖：
#   SUDO_PASS    sudo 密码（若 docker 需要 sudo）；设了则自动 `echo $SUDO_PASS | sudo -S`
#   SECRET_KEY   复用已有的 Django SECRET_KEY（未设则首次随机生成，并写进 .docker_env）
#   ALLOWED_HOSTS  部署机 IP 或域名（默认 localhost,127.0.0.1）

set -euo pipefail

cd "$(dirname "$0")/.."

# ----------------------------- 参数解析 -----------------------------
DUMP_FILE=""
RESET_ADMIN=0
DO_STOP=0
for arg in "$@"; do
  case "$arg" in
    --dump) DUMP_FILE="__next__";;
    --reset-admin) RESET_ADMIN=1;;
    --stop) DO_STOP=1;;
    *) if [ "$DUMP_FILE" = "__next__" ]; then DUMP_FILE="$arg"; fi;;
  esac
done
[ "$DUMP_FILE" = "__next__" ] && DUMP_FILE=""

ENV_FILE=".docker_env"

# ----------------------------- 提权与命令封装 -----------------------------
# 判定 docker 是否需要 sudo；优先直连，失败才走 sudo。
DOCKER_CMD="docker"
if ! docker info >/dev/null 2>&1; then
  if [ -n "${SUDO_PASS:-}" ]; then
    DOCKER_CMD="echo \"$SUDO_PASS\" | sudo -S docker"
  else
    echo "[deploy] docker 需要提权，请设置 SUDO_PASS 环境变量（sudo 密码）" >&2
    exit 1
  fi
fi

run() {
  # 用 sh -c 执行已拼好的命令串（含管道），保证 SUDO_PASS 不被泄露到 ps。
  sh -c "$1"
}

# ----------------------------- .docker_env -----------------------------
gen_env() {
  local secret="${SECRET_KEY:-}"
  if [ -z "$secret" ]; then
    # 首次部署随机生成；若需复用旧库签名，请用 SECRET_KEY 环境变量传入原值。
    secret="$(openssl rand -base64 48 2>/dev/null || python3 -c 'import secrets;print(secrets.token_urlsafe(48))')"
  fi
  local allowed="${ALLOWED_HOSTS:-localhost,127.0.0.1}"
  cat > "$ENV_FILE" <<EOF
SECRET_KEY=$secret
DEBUG=False
ALLOWED_HOSTS=$allowed
CORS_ALLOWED_ORIGINS=http://localhost:18081,http://127.0.0.1:18081
CSRF_TRUSTED_ORIGINS=http://localhost:18081,http://127.0.0.1:18081
APP_USE_HTTPS=False
TRUST_PROXY_SSL_HEADER=False
MYSQL_ROOT_PASSWORD=ITadmin@123
DB_NAME=testhub
DB_USER=testhub
DB_PASSWORD=ITadmin@123
FRONTEND_PORT=18081
BACKEND_PORT=18181
DOCKER_NAMESPACE=testhub
IMAGE_VERSION=latest
SCHEDULER_INTERVAL=300
SCHEMA_SETUP_ENABLED=False
RUN_COLLECTSTATIC=True
REDIS_URL=redis://redis:6379/0
AI_OBSERVABILITY_ENABLED=True
OPENAPI_IMPORT_MAX_BYTES=5242880
EOF
  echo "[deploy] 已生成 $ENV_FILE（密码统一 ITadmin@123）"
}

# ----------------------------- 停止 -----------------------------
if [ "$DO_STOP" = "1" ]; then
  echo "[deploy] 停止所有服务（不删数据卷）"
  run "$DOCKER_CMD compose --env-file $ENV_FILE stop"
  exit 0
fi

# ----------------------------- 首次生成配置 -----------------------------
if [ ! -f "$ENV_FILE" ]; then
  gen_env
else
  echo "[deploy] 已存在 $ENV_FILE，跳过生成"
fi

# ----------------------------- 归一化换行（防 Windows 传输带入 CRLF） -----------------------------
# 源码从 Windows 检出/打包时，*.sh 可能带 CRLF，容器内 shebang 会解析失败
# （报 exec /entrypoint.sh: no such file or directory）。构建前统一去掉 \r。
if command -v sed >/dev/null 2>&1; then
  for f in backend/entrypoint.sh backend/scheduler-loop.sh; do
    [ -f "$f" ] && sed -i 's/\r$//' "$f"
  done
  echo "[deploy] 已归一化脚本换行符"
fi

# ----------------------------- 构建 -----------------------------
echo "[deploy] 构建镜像"
run "$DOCKER_CMD compose --env-file $ENV_FILE build"

# ----------------------------- 起 DB/Redis 等健康 -----------------------------
echo "[deploy] 启动 mysql + redis 并等待健康"
run "$DOCKER_CMD compose --env-file $ENV_FILE up -d mysql redis"
for i in $(seq 1 60); do
  if run "$DOCKER_CMD compose --env-file $ENV_FILE ps mysql" | grep -q "(healthy)"; then
    break
  fi
  sleep 3
done

# ----------------------------- 导入业务库（可选） -----------------------------
if [ -n "$DUMP_FILE" ]; then
  echo "[deploy] 导入业务库：$DUMP_FILE"
  run "$DOCKER_CMD compose --env-file $ENV_FILE exec -T mysql sh -c 'exec mysql -uroot -p\"\$MYSQL_ROOT_PASSWORD\"' < $DUMP_FILE"
fi

# ----------------------------- 起其余服务 -----------------------------
echo "[deploy] 启动 backend / scheduler / frontend"
run "$DOCKER_CMD compose --env-file $ENV_FILE up -d"

# 等 backend 起来
sleep 5

# ----------------------------- 重置 admin 密码 -----------------------------
reset_admin() {
  run "$DOCKER_CMD compose --env-file $ENV_FILE exec -T backend python manage.py shell -c \
    \"from apps.users.models import User; u=User.objects.filter(is_superuser=True).order_by('id').first(); u.set_password('ITadmin@123'); u.save(); print('[deploy] admin 密码已重置:', u.username)\""
}

if [ "$RESET_ADMIN" = "1" ]; then
  reset_admin
fi

# ----------------------------- 收尾提示 -----------------------------
echo
echo "[deploy] 完成。状态："
run "$DOCKER_CMD compose --env-file $ENV_FILE ps"
echo
echo "  前端: http://<本机IP>:18081   (admin / ITadmin@123)"
echo "  后端: http://<本机IP>:18181/api/docs/"
echo "  健康: curl -s http://<本机IP>:18081/health"
echo "  停止: ./deploy-testhub.sh --stop   (不会删数据)"
