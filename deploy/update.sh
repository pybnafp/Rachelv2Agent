#!/usr/bin/env bash
# =============================================================================
# Rachel v2 — 发布更新脚本（假设 init_server.sh 已执行过一次）
# !! 在【服务器】/root/Rachelv2Agent 下运行；代码已上传/更新到该目录。
#   幂等：重复运行安全。不触碰 nginx 现有站点。
# =============================================================================
set -euo pipefail

APP_DIR="/root/Rachelv2Agent"
PIP="/root/miniconda3/envs/rachel-v2/bin/pip"
ALEMBIC="/root/miniconda3/envs/rachel-v2/bin/alembic"
WEB_ROOT="/var/www/rachelv2"

echo "== [1/5] pip install =="
"$PIP" install -e "$APP_DIR/backend[dev]"

echo "== [2/5] alembic upgrade head =="
cd "$APP_DIR/backend"
"$ALEMBIC" upgrade head

echo "== [3/5] 前端构建 =="
cd "$APP_DIR/frontend"
npm ci
npm run build

echo "== [4/5] 部署静态文件 =="
cd "$APP_DIR/frontend"
mkdir -p "$WEB_ROOT"
cp -r dist/* "$WEB_ROOT"/

echo "== [5/5] 重启服务 + reload nginx =="
systemctl restart rachel-api rachel-worker
nginx -t && systemctl reload nginx

echo "== 更新完成 =="
