#!/usr/bin/env bash
# =============================================================================
# Rachel v2 — 服务器初始化 runbook（幂等，可重复执行）
#
# !! 本脚本在【服务器】上运行（Ubuntu 22.04，root），而非本地开发机：
#      scp deploy/init_server.sh root@SERVER:/root/Rachelv2Agent/deploy/
#      ssh root@SERVER 'bash /root/Rachelv2Agent/deploy/init_server.sh'
#
# 步骤（每步均有存在性守卫，重复运行安全）：
#   1. apt 安装 redis-server / postgresql（nginx 已装则跳过）
#   2. PG 创建角色 rachel + 数据库 rachel（DO block 幂等，密码来自 .env 或 PG_PASSWORD）
#   3. .env 生成（若缺失）：PG 密码 / JWT_SECRET 随机
#   4. miniconda 安装（TUNA 镜像，已存在跳过）
#   5. conda env create rachel-v2（已存在跳过）
#   6. pip install -e "backend[dev]"
#   7. alembic upgrade head
#   8. 前端 npm ci && npm run build，dist -> /var/www/rachelv2
#   9. systemd 单元安装并 enable --now
#  10. nginx 站点启用（sites-available + symlink + nginx -t + reload）
# 注意：绝不触碰现有 80/443 站点配置。
# =============================================================================
set -euo pipefail

APP_DIR="/root/Rachelv2Agent"
ENV_FILE="$APP_DIR/.env"
CONDA_ENV="rachel-v2"
CONDA_BIN="/root/miniconda3/bin/conda"
PY="/root/miniconda3/envs/$CONDA_ENV/bin/python"
WEB_ROOT="/var/www/rachelv2"

echo "== [1/10] apt: redis-server / postgresql =="
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y redis-server postgresql
command -v nginx >/dev/null 2>&1 || apt-get install -y nginx
systemctl enable --now redis-server
systemctl enable --now postgresql

echo "== [2/10] 生成 .env（若缺失）=="
if [ ! -f "$ENV_FILE" ]; then
  PG_PASSWORD="${PG_PASSWORD:-$(openssl rand -hex 16)}"
  JWT_SECRET="$(openssl rand -hex 32)"
  cat > "$ENV_FILE" <<EOF
DATABASE_URL=postgresql+psycopg2://rachel:${PG_PASSWORD}@127.0.0.1:5432/rachel
REDIS_URL=redis://127.0.0.1:6379/0
JWT_SECRET=${JWT_SECRET}
DATA_DIR=/root/Rachelv2Agent/data/jobs
PUBCHEM_OFFLINE=true
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-pro
EOF
  chmod 600 "$ENV_FILE"
  echo "   已生成 $ENV_FILE"
else
  echo "   $ENV_FILE 已存在，跳过"
fi

# 从 .env 读取 PG 密码（用于建角色）
PG_PASSWORD="$(grep -E '^DATABASE_URL=' "$ENV_FILE" | sed -E 's|.*://rachel:([^@]*)@.*|\1|')"

echo "== [3/10] PostgreSQL: 角色 rachel + 数据库 rachel（幂等 DO block）=="
su - postgres -c "psql -v ON_ERROR_STOP=1" <<EOF
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'rachel') THEN
    CREATE ROLE rachel LOGIN PASSWORD '${PG_PASSWORD}';
  END IF;
END
\$\$;
EOF
su - postgres -c "psql -tAc \"SELECT 1 FROM pg_database WHERE datname='rachel'\"" | grep -q 1 \
  || su - postgres -c "createdb -O rachel rachel"

echo "== [4/10] miniconda（TUNA 镜像，已存在跳过）=="
if [ ! -x "$CONDA_BIN" ]; then
  wget -q https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda/Miniconda3-latest-Linux-x86_64.sh -O /tmp/miniconda.sh
  bash /tmp/miniconda.sh -b -p /root/miniconda3
  rm -f /tmp/miniconda.sh
else
  echo "   miniconda 已安装，跳过"
fi

echo "== [5/10] conda env: $CONDA_ENV（已存在跳过）=="
if [ ! -x "$PY" ]; then
  "$CONDA_BIN" create -y -n "$CONDA_ENV" python=3.11
else
  echo "   conda env 已存在，跳过"
fi
PIP="/root/miniconda3/envs/$CONDA_ENV/bin/pip"

echo "== [6/10] pip install -e backend[dev] =="
"$PIP" install -e "$APP_DIR/backend[dev]"

echo "== [7/10] alembic upgrade head =="
cd "$APP_DIR/backend"
"/root/miniconda3/envs/$CONDA_ENV/bin/alembic" upgrade head

echo "== [8/10] 前端构建 + 部署静态文件 =="
cd "$APP_DIR/frontend"
npm ci
npm run build
mkdir -p "$WEB_ROOT"
cp -r dist/* "$WEB_ROOT"/

echo "== [9/10] systemd 单元 =="
cp "$APP_DIR/deploy/systemd/rachel-api.service" /etc/systemd/system/
cp "$APP_DIR/deploy/systemd/rachel-worker.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now rachel-api rachel-worker

echo "== [10/10] nginx 站点（8080，独立 server block）=="
cp "$APP_DIR/deploy/nginx-rachelv2.conf" /etc/nginx/sites-available/rachelv2
ln -sf /etc/nginx/sites-available/rachelv2 /etc/nginx/sites-enabled/rachelv2
nginx -t
systemctl reload nginx

echo "== 初始化完成 =="
echo "   站点: http://<server>:8080  API: http://<server>:8080/api/health"
echo "   日志: journalctl -u rachel-api -f / journalctl -u rachel-worker -f"
