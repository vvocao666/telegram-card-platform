# 部署指南

## 部署版本

普通云服务器部署只使用 Cloud Deploy：

```text
Cloud Deploy / 当前 main
```

Cloud Deploy 是唯一标准部署版本，`main` 是 Cloud Deploy 的滚动最新源码。它包含当前全部通用功能和 Bug 修复，但默认不依赖 Windows RTX5070、Tailscale 或 Remote OCR。

owner-hybrid 仅用于作者本人环境：

```text
owner-hybrid = Cloud Deploy + RTX5070 / Tailscale / Remote OCR
```

## 支持系统

- Ubuntu 22.04
- Ubuntu 24.04
- Debian 12

## 安装依赖

```bash
export APP_DIR=/opt/telegram-card-platform
sudo git clone https://github.com/vvocao666/telegram-card-platform.git "$APP_DIR"
cd "$APP_DIR"

sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip git tesseract-ocr
python3 -m venv .venv
.venv/bin/python3 -m pip install --upgrade pip
.venv/bin/python3 -m pip install -r requirements.txt
```

## 配置

```bash
cp .env.example .env
nano .env
```

必填：

```env
BOT_TOKEN=
OCR_SPACE_API_KEY=
```

或使用多 Key：

```env
OCR_SPACE_API_KEYS=key1,key2,key3
```

普通云服务器必须保持：

```env
REMOTE_OCR_ENABLED=false
REMOTE_OCR_URL=
```

owner-hybrid 才允许开启：

```env
REMOTE_OCR_ENABLED=true
REMOTE_OCR_URL=http://100.81.208.104:8000
REMOTE_OCR_TIMEOUT=1.5
```

## systemd

```bash
sudo mkdir -p /etc/telegram-card-platform
printf 'APP_DIR=%s\nPYTHON_BIN=.venv/bin/python3\n' "$APP_DIR" | sudo tee /etc/telegram-card-platform/service.env
sudo cp systemd/telegram-card-platform.service /etc/systemd/system/telegram-card-platform.service
sudo systemctl daemon-reload
sudo systemctl enable telegram-card-platform
sudo systemctl start telegram-card-platform
sudo systemctl status telegram-card-platform --no-pager
```

## 验证

```bash
cd "$APP_DIR"
.venv/bin/python3 -m compileall -q bot.py config handlers services storage utils tests
.venv/bin/python3 -m pytest
systemctl is-active telegram-card-platform
journalctl -u telegram-card-platform -n 100 --no-pager
```

## 更新

```bash
cd "$APP_DIR"
git pull --ff-only origin main
.venv/bin/python3 -m pip install -r requirements.txt
.venv/bin/python3 -m compileall -q bot.py config handlers services storage utils tests
sudo systemctl restart telegram-card-platform
```

## 备份

```bash
bash scripts/backup_data.sh
```

手工完整备份示例：

```bash
ts=$(date +%Y%m%d_%H%M%S)
backup=/root/backups/telegram-card-platform_$ts
mkdir -p "$backup"
rsync -a --exclude .venv /opt/telegram-card-platform/ "$backup/project/"
cp /opt/telegram-card-platform/.env "$backup/.env"
cp /opt/telegram-card-platform/outputs/ledger.sqlite3 "$backup/ledger.sqlite3"
cp /etc/systemd/system/telegram-card-platform.service "$backup/telegram-card-platform.service"
```

## 回滚

优先恢复最近一次完整备份：

```bash
sudo systemctl stop telegram-card-platform
rsync -a /root/backups/telegram-card-platform_YYYYMMDD_HHMMSS/project/ /opt/telegram-card-platform/
cp /root/backups/telegram-card-platform_YYYYMMDD_HHMMSS/.env /opt/telegram-card-platform/.env
sudo systemctl start telegram-card-platform
```

不要把 v120 或 v1.3 当成最新稳定版。它们只保留为历史归档。
