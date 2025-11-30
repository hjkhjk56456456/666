#!/bin/bash
set -euo pipefail

# 配置
APP_DIR="/var/www/youtube-downloader"
REPO_URL="https://github.com/yourusername/youtube-downloader.git"  # 替换为实际仓库URL
VENV_DIR="$APP_DIR/venv"
LOG_FILE="$APP_DIR/deploy.log"

# 日志函数
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "开始部署YouTube Downloader应用..."

# 1. 安装依赖
log "检查系统依赖..."
sudo apt update -qq > /dev/null
sudo apt install -y -qq python3 python3-pip python3-venv nginx git > /dev/null

# 2. 创建应用目录
log "准备应用目录..."
sudo mkdir -p "$APP_DIR"
sudo chown -R $USER:$USER "$APP_DIR"

# 3. 拉取代码
if [ -d "$APP_DIR/.git" ]; then
    log "更新代码..."
    cd "$APP_DIR"
    git pull origin main
else
    log "克隆代码仓库..."
    git clone "$REPO_URL" "$APP_DIR"
fi

# 4. 创建虚拟环境
log "配置Python虚拟环境..."
cd "$APP_DIR"
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi

# 5. 安装Python依赖
log "安装依赖包..."
"$VENV_DIR/bin/pip" install --upgrade pip > /dev/null
"$VENV_DIR/bin/pip" install -r requirements.txt > /dev/null

# 6. 配置环境变量
log "设置环境变量..."
if [ ! -f "$APP_DIR/.env" ]; then
    cat > "$APP_DIR/.env" << EOF
FLASK_APP=app.py
FLASK_ENV=production
HOST=127.0.0.1
PORT=8000
TEMP_DOWNLOAD_DIR=/tmp/youtube-downloads
EOF
fi

# 7. 配置Nginx
log "配置Nginx..."
sudo cp "$APP_DIR/nginx.conf" /etc/nginx/sites-available/youtube-downloader
sudo ln -sf /etc/nginx/sites-available/youtube-downloader /etc/nginx/sites-enabled/
sudo nginx -t > /dev/null || { log "Nginx配置错误"; exit 1; }
sudo systemctl restart nginx

# 8. 配置Systemd服务
log "配置系统服务..."
sudo cp "$APP_DIR/youtube-downloader.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable youtube-downloader
sudo systemctl restart youtube-downloader

# 9. 设置防火墙
log "配置防火墙..."
sudo ufw allow 'Nginx Full' > /dev/null

# 10. 健康检查
log "执行健康检查..."
if curl -s "http://127.0.0.1/api/health" | grep -q "healthy"; then
    log "部署成功！应用已启动并正常运行"
else
    log "部署警告：应用健康检查失败，请检查日志"
    exit 1
fi

log "部署完成"