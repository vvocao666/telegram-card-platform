# 维护指南

## 日常检查

```bash
systemctl is-active telegram-card-platform
journalctl -u telegram-card-platform --since "1 hour ago"
```

## 修改前

```bash
git status --short --branch
git log -5 --oneline --decorate
python -m pytest
python -m compileall -q bot.py config handlers services storage utils tests
python scripts/check_deploy_consistency.py
```

不要提交 `.env`、数据库、日志、运行输出、审计图片或备份。任何 OCR 改动必须保持不猜卡、不跨卡拼接，并通过真实样本 benchmark。

## 备份与恢复

```bash
bash scripts/backup_data.sh
```

生产部署前备份项目、`.env`、`outputs/ledger.sqlite3`、`outputs/` 和 systemd service。恢复细节见 [ROLLBACK.md](ROLLBACK.md)。

## 常见问题

- 服务未启动：检查 `.env`、依赖和 `journalctl -u telegram-card-platform`。
- OCR 失败：检查 OCR.space 配置、网络、冷却日志与图片尺寸。
- Owner Hybrid 离线：确认 Windows Worker 正常；机器人会自动回退 OCR.space。
- 账本异常：检查 `LEDGER_DB_PATH`，不要覆盖或删除生产数据库。
