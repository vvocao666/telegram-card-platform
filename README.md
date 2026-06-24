# Telegram Card Platform

## 推荐版本

普通云服务器部署：`v2.8.0-cloud-deploy`

我本人 RTX5070 专用：`owner-hybrid` 最新版

旧稳定版：`v1.3.0-ocr-learning-plus` 已归档，不再作为最新推荐部署版本。

`v2.8.0-cloud-deploy` 是从当前最新版整理出的通用云服务器稳定部署版。它保留最近修复过的 OCR 规则、PUBG/PSN 分类、S07 前缀、文本忽略、状态面板、学习与缓存能力，但默认关闭本地 Windows RTX5070 OCR Worker、Tailscale、Remote OCR、Hybrid OCR。

普通 Ubuntu / Debian 云服务器默认只走 OCR.space / 云端 OCR，不需要本地电脑。

## 永久版本规则

Cloud Deploy 是唯一标准版，永远代表当前最新、功能最完整、普通用户拿到源码即可直接部署的版本。以后新增任何通用功能、OCR 修复、管理员命令、通知能力、文本优化、排序优化、换行拼接优化、S07 识别优化和 bug 修复，默认必须进入 Cloud Deploy。

owner-hybrid 是作者私人版本，等于 Cloud Deploy 乘以 RTX5070 本地混合识别。唯一允许只存在于 owner-hybrid 的能力是 Windows RTX5070 OCR Worker、`REMOTE_OCR_URL`、Tailscale、本地 GPU 混合识别。

如果以后需要我本人环境的 Hybrid OCR，可在 `.env` 中开启：

```env
REMOTE_OCR_ENABLED=true
REMOTE_OCR_URL=http://100.81.208.104:8000
```

## 项目介绍

Telegram Card Platform 是一个可复用的 Telegram 卡密机器人框架，包含图片 OCR、PUBG/PSN 卡密解析、去重提醒、OCR 学习、记账、广播、管理员权限、缓存、状态面板、备份、回滚和 systemd 部署。

## 当前功能

- Telegram 图片 / 照片 / 相册卡密识别。
- OCR.space 云端 OCR 流程。
- `REMOTE_OCR_ENABLED=false` 默认关闭本地 RTX5070 Hybrid OCR。
- PUBG / PSN 图片级互斥，防止 PUBG 后半段被截成 PSN。
- 任意 `S07XXX-XXXX-XXXX-XXXXX` 识别为 PUBG。
- PUBG 断行拼接和行序重建。
- PSN 独立 `XXXX-XXXX-XXXX` 识别。
- 文本消息不自动重复提取卡密，避免刷屏。
- 输出排序、稳定去重、重复提醒。
- OCR 学习、字体模板、今日 OCR 缓存，OWNER 私聊可直接发送“学习卡密”粘贴人工真值。
- `/状态`、`/status`、`/ocr_status` 状态面板。
- `/remote_ocr_status` 远程 OCR 状态，Cloud Deploy 默认显示远程未启用。
- Broadcast：OWNER 私聊发送 `/broadcast` 或“广播”，选择一个或多个群组，预览后确认发送。
- Notify All：OWNER/admin 在群内发送“通知所有人”、`/notify_all` 或 `/at_all`，只 @ 当前群最近30天活跃成员。
- `/broadcast_preview` 广播预览，`/broadcast_cancel` 取消广播任务，`/notify_members` 查看当前群成员缓存。
- 记账、查账、清账、暂停/开启记账。
- Owner 广播、管理员权限、审计转发。
- systemd 服务、备份脚本、GitHub CI。

## 目录结构

```text
bot.py                  # 启动入口和 handler 注册
config/                 # 配置、日志、常量
handlers/               # Telegram Update handler
services/               # OCR、记账、广播、转发、价格等服务
storage/                # 数据库与 repository
utils/                  # 通用工具
tests/                  # 自动化测试
scripts/                # 备份、部署、恢复脚本
systemd/                # systemd 服务模板
docs/                   # 项目文档
feature_backups/        # 历史稳定备份
```

## 快速部署

一键安装：

```bash
curl -fsSL https://raw.githubusercontent.com/vvocao666/telegram-card-platform/main/install.sh | sudo bash
```

手动部署：

```bash
export APP_DIR=/opt/telegram-card-platform
sudo git clone https://github.com/vvocao666/telegram-card-platform.git "$APP_DIR"
cd "$APP_DIR"
git checkout v2.8.0-cloud-deploy

sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip git tesseract-ocr
python3 -m venv .venv
.venv/bin/python3 -m pip install --upgrade pip
.venv/bin/python3 -m pip install -r requirements.txt

cp .env.example .env
nano .env
```

最少需要配置：

```env
BOT_TOKEN=
OWNER_CHAT_ID=
OCR_SPACE_API_KEY=
# 或 OCR_SPACE_API_KEYS=
REMOTE_OCR_ENABLED=false
```

安装 systemd：

```bash
sudo mkdir -p /etc/telegram-card-platform
printf 'APP_DIR=%s\nPYTHON_BIN=.venv/bin/python3\n' "$APP_DIR" | sudo tee /etc/telegram-card-platform/service.env
sudo cp systemd/telegram-card-platform.service /etc/systemd/system/telegram-card-platform.service
sudo systemctl daemon-reload
sudo systemctl enable telegram-card-platform
sudo systemctl start telegram-card-platform
sudo systemctl status telegram-card-platform --no-pager
```

## 更新

```bash
cd /opt/telegram-card-platform
git fetch --tags
git checkout v2.8.0-cloud-deploy
.venv/bin/python3 -m pip install -r requirements.txt
.venv/bin/python3 -m compileall -q bot.py config handlers services storage utils tests
sudo systemctl restart telegram-card-platform
```

也可以使用：

```bash
sudo bash deploy.sh
```

## 日志查看

```bash
journalctl -u telegram-card-platform -f
journalctl -u telegram-card-platform -n 100 --no-pager
```

## 重启服务

```bash
sudo systemctl restart telegram-card-platform
sudo systemctl status telegram-card-platform --no-pager
```

## 备份

Linux：

```bash
bash scripts/backup_data.sh
```

Windows PowerShell：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/backup.ps1
```

## 回滚

普通云服务器推荐回滚到：

```bash
cd /opt/telegram-card-platform
sudo systemctl stop telegram-card-platform
git fetch --tags
git checkout v2.8.0-cloud-deploy
.venv/bin/python3 -m pip install -r requirements.txt
sudo systemctl start telegram-card-platform
```

历史归档版本：

```bash
git checkout v1.3.0-ocr-learning-plus
```

`v1.3.0-ocr-learning-plus` 仅作为旧稳定归档，不再是最新推荐通用部署版本。

## 文档

- `DEPLOY.md`：部署指南。
- `ROLLBACK.md`：回滚说明。
- `docs/STABLE_RELEASES.md`：稳定版本选择。
- `docs/RELEASE_POLICY.md`：发布规范。
- `docs/OCR_CORRECTION.md`：OCR 纠错和学习说明。
