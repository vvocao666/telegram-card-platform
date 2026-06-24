# 回滚说明

## 当前推荐通用稳定版

普通云服务器推荐回滚到：

```text
v2.8.0-cloud-deploy
```

这是当前最新版整理出的通用云服务器部署版，默认关闭：

- Windows RTX5070 OCR Worker
- Tailscale
- Remote OCR
- Hybrid OCR
- 本地显卡优先识别

但保留：

- OCR.space 云端 OCR
- PUBG/PSN 图片级互斥
- 任意 `S07XXX-XXXX-XXXX-XXXXX` PUBG 前缀规则
- PUBG 断行拼接
- 文本消息忽略
- 去重、排序、Validator
- OCR 学习、今日缓存、状态面板
- 记账、广播、管理员权限
- `通知所有人`、`/broadcast_preview`、`/broadcast_cancel`

## 永久规则

以后不要再维护多个“稳定版”。Cloud Deploy 是唯一标准版，代表当前最新功能完整版本。owner-hybrid 只是在 Cloud Deploy 基础上额外开启 RTX5070 本地混合识别。

## 回滚到通用云服务器版

```bash
cd /opt/telegram-card-platform
sudo systemctl stop telegram-card-platform
git fetch --tags
git checkout v2.8.0-cloud-deploy
.venv/bin/python3 -m pip install -r requirements.txt
.venv/bin/python3 -m compileall -q bot.py config handlers services storage utils tests
sudo systemctl start telegram-card-platform
sudo systemctl status telegram-card-platform --no-pager
```

确认 `.env` 中：

```env
REMOTE_OCR_ENABLED=false
```

## 回滚到旧归档版本

`v1.3.0-ocr-learning-plus` 已归档，不再作为最新推荐部署版本。只有在需要回到 Hybrid OCR 之前的历史状态时使用：

```bash
cd /opt/telegram-card-platform
sudo systemctl stop telegram-card-platform
git fetch --tags
git checkout v1.3.0-ocr-learning-plus
.venv/bin/python3 -m pip install -r requirements.txt
sudo systemctl start telegram-card-platform
```

## Owner Hybrid 版本

`owner-hybrid` / `v2.x-hybrid` 版本只适合我本人环境：

- Windows RTX5070 OCR Worker
- Tailscale
- `REMOTE_OCR_URL`
- Hybrid OCR

普通云服务器不要把 owner 专用版本作为默认部署目标。

## 数据保护

回滚时不要删除：

- `.env`
- `outputs/`
- `outputs/ledger.sqlite3`
- `feature_backups/`
- `/root/backups/`
