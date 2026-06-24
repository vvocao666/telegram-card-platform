# 部署指南

## 推荐部署版本

普通云服务器部署：`v2.8.0-cloud-deploy`

我本人 RTX5070 专用：`owner-hybrid` 最新版

旧稳定版：`v1.3.0-ocr-learning-plus` 已归档，不再作为最新推荐部署版本。

## 版本选择

Cloud Deploy 是唯一标准版。新服务器部署完成后，默认应该具备当前所有通用功能，不需要额外补丁、手工添加脚本或额外 `git pull`。

Cloud Deploy 必须包含最新 OCR 修复、PUBG/PSN 互斥、S07 任意前缀、换行拼接、文本忽略、排序、去重、Validator、学习流程、缓存、状态面板、`/remote_ocr_status`、Broadcast、Notify All、`/broadcast_preview`、`/broadcast_cancel`、`/notify_members` 和所有管理员命令。

### 普通云服务器

请选择：

```text
v2.8.0-cloud-deploy
```

适用环境：

- Ubuntu 22.04
- Ubuntu 24.04
- Debian 12
- 普通 2C/1G 或以上云服务器
- 只使用 OCR.space / 云端 OCR
- 没有本地 Windows GPU
- 没有 Tailscale
- 不依赖 `REMOTE_OCR_URL`

默认配置：

```env
REMOTE_OCR_ENABLED=false
```

### Owner Hybrid OCR

只有我本人当前环境才需要开启：

```env
REMOTE_OCR_ENABLED=true
REMOTE_OCR_URL=http://100.81.208.104:8000
```

该模式依赖：

- Windows RTX5070 OCR Worker
- Tailscale
- Remote OCR API
- 本地显卡优先识别

普通用户不要直接部署 `owner-hybrid` 版本。

## 服务器准备

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip git tesseract-ocr
```

## 拉取代码

```bash
export APP_DIR=/opt/telegram-card-platform
sudo git clone https://github.com/vvocao666/telegram-card-platform.git "$APP_DIR"
cd "$APP_DIR"
git fetch --tags
git checkout v2.8.0-cloud-deploy
```

也可以直接运行：

```bash
curl -fsSL https://raw.githubusercontent.com/vvocao666/telegram-card-platform/main/install.sh | sudo bash
```

## 安装依赖

```bash
python3 -m venv .venv
.venv/bin/python3 -m pip install --upgrade pip
.venv/bin/python3 -m pip install -r requirements.txt
```

## 配置 `.env`

```bash
cp .env.example .env
nano .env
```

必填：

```env
BOT_TOKEN=
OCR_SPACE_API_KEY=
```

推荐：

```env
OWNER_CHAT_ID=
OCR_SPACE_API_KEYS=
LEDGER_DB_PATH=outputs/ledger.sqlite3
REMOTE_OCR_ENABLED=false
```

不要把生产 `.env` 提交到 GitHub。

## 安装 systemd

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
cd /opt/telegram-card-platform
.venv/bin/python3 -m pytest
.venv/bin/python3 -m compileall -q bot.py config handlers services storage utils tests
```

机器人内可以发送：

```text
/状态
/status
/ocr_status
/remote_ocr_status
```

owner 可以在私聊中使用广播命令：

```text
/broadcast
广播
/broadcast_preview
/broadcast_cancel
```

owner/admin 可以在群内使用通知命令：

```text
通知所有人
/notify_all
/at_all
/notify_members
```

普通云部署时状态面板中 Remote OCR 应显示未启用或离线，但 OCR.space 备用仍可用。

## 查看日志

```bash
journalctl -u telegram-card-platform -f
journalctl -u telegram-card-platform -n 100 --no-pager
```

## 更新

```bash
cd /opt/telegram-card-platform
sudo systemctl stop telegram-card-platform
git fetch --tags
git checkout v2.8.0-cloud-deploy
.venv/bin/python3 -m pip install -r requirements.txt
.venv/bin/python3 -m compileall -q bot.py config handlers services storage utils tests
sudo systemctl start telegram-card-platform
```

或者：

```bash
sudo bash deploy.sh
```

## 备份

部署前建议备份：

```bash
ts=$(date +%Y%m%d_%H%M%S)
backup=/root/backups/before_deploy_$ts
mkdir -p "$backup"
cp -a /opt/telegram-card-platform "$backup/project"
cp -a /etc/systemd/system/telegram-card-platform.service "$backup/telegram-card-platform.service"
```

## 回滚

```bash
cd /opt/telegram-card-platform
sudo systemctl stop telegram-card-platform
git fetch --tags
git checkout v2.8.0-cloud-deploy
.venv/bin/python3 -m pip install -r requirements.txt
sudo systemctl start telegram-card-platform
```

如果需要回到旧归档版本：

```bash
git checkout v1.3.0-ocr-learning-plus
sudo systemctl restart telegram-card-platform
```
