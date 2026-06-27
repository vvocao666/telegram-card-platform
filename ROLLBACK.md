# 回滚说明

## 当前标准

当前唯一推荐部署版本是：

```text
Cloud Deploy / v2.8.0-cloud-deploy / 当前 main
```

Cloud Deploy 代表当前最新通用功能和全部通用 Bug 修复。

## 优先回滚方式

生产回滚优先使用服务器备份，而不是旧 tag：

```bash
sudo systemctl stop telegram-card-platform
rsync -a /root/backups/backup_name/project/ /opt/telegram-card-platform/
cp /root/backups/backup_name/.env /opt/telegram-card-platform/.env
cp /root/backups/backup_name/ledger.sqlite3 /opt/telegram-card-platform/outputs/ledger.sqlite3
sudo systemctl start telegram-card-platform
```

## Cloud Deploy 与 owner-hybrid

普通云服务器：

```env
REMOTE_OCR_ENABLED=false
REMOTE_OCR_URL=
```

作者本人环境：

```env
REMOTE_OCR_ENABLED=true
REMOTE_OCR_URL=http://100.81.208.104:8000
```

如果不使用本地 RTX5070 / Tailscale / Remote OCR，只需要关闭 `.env` 中的 Remote OCR，不需要回退到旧版本。

## 历史版本

`v1.3.0-ocr-learning-plus` 已归档，不再作为最新推荐部署版本。

`strict-v120-owner-broadcast-no-trx` / `feature_backups/v120_stable` 只作为历史重构前备份。

只有在需要回到旧行为做事故排查时，才使用历史 tag。
