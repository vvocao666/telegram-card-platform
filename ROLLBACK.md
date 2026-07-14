# 回滚说明

生产回滚优先使用本次部署前的服务器备份，而不是直接切换旧 tag。备份必须保留项目目录、`.env`、`outputs/ledger.sqlite3`、`outputs/` 与 systemd service。

## 从服务器备份恢复

```bash
sudo systemctl stop telegram-card-platform
sudo rsync -a /root/backups/telegram-card-platform_before_YYYYMMDD_HHMMSS/project/ /opt/telegram-card-platform/
sudo cp /root/backups/telegram-card-platform_before_YYYYMMDD_HHMMSS/.env /opt/telegram-card-platform/.env
sudo cp /root/backups/telegram-card-platform_before_YYYYMMDD_HHMMSS/ledger.sqlite3 /opt/telegram-card-platform/outputs/ledger.sqlite3
sudo systemctl daemon-reload
sudo systemctl start telegram-card-platform
sudo systemctl status telegram-card-platform --no-pager
```

实际备份目录必须以部署时输出的路径为准。恢复前后都不要删除当前 `.env`、数据库或 `outputs/`。

## Cloud Deploy 与 Owner Hybrid

两者始终使用相同代码 commit。普通云服务器保持：

```env
REMOTE_OCR_ENABLED=false
REMOTE_OCR_URL=
```

Owner Hybrid 仅在私有 `.env` 启用自己的 Remote OCR。若 Windows Worker 或网络不可用，不需要回滚业务代码，机器人会自动回退 OCR.space。

## Git 回滚

仅当确认某个已发布 commit 是问题根因时使用：

```bash
cd /opt/telegram-card-platform
git log --oneline -10
git checkout <known-good-commit>
sudo systemctl restart telegram-card-platform
```

Git 回滚前也必须完整备份；恢复完成后检查服务和日志。
