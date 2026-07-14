# Telegram Card Platform

## 正式生产版本

`main` 是唯一的业务代码源，也是 Cloud Deploy 的滚动正式版本。Cloud Deploy 与 Owner Hybrid 必须使用同一个 Git commit SHA、同一套业务代码、同一套 OCR 规则和同一数据库行为。

```text
Cloud Deploy = main + REMOTE_OCR_ENABLED=false
Owner Hybrid = main + 私有 .env 中开启 RTX5070 Remote OCR
```

Owner Hybrid 不维护单独的业务分支。它仅增加 Windows RTX5070 Worker、Tailscale 或私有 Remote OCR 地址等环境配置；Remote OCR 不可用时自动回退 OCR.space。

## 功能

- 图片、相册和图片文件 PUBG / PSN 卡密识别
- `S07` 加三位数字 PUBG 前缀、相邻 OCR 行换行重建、PUBG/PSN 图片级互斥
- Remote OCR 优先、OCR.space 自动回退、按需 OpenCV 预处理、缓存、限流和稳定批次排序
- 服务器 OCR 审计、审计副机器人转发、私有 benchmark 与人工复核入口
- 记账、汇率、费率、日切、账单、价格查询与 TRC20 地址校验
- owner 群广播、当前群通知所有人、群欢迎、状态和 OCR 调试命令
- systemd、备份、恢复、Cloud Deploy 与 Owner Hybrid 部署入口

普通文本不会触发 OCR；无卡图片保持静默。OCR 不猜卡、不跨行或跨卡拼接，无法确认时进入复核而不是输出不可追溯的卡密。

## Cloud Deploy

适用于 Ubuntu 22.04、Ubuntu 24.04 与 Debian 12，不需要 Windows、RTX5070、Tailscale 或私有 Remote OCR。

```bash
git clone https://github.com/vvocao666/telegram-card-platform.git /opt/telegram-card-platform
cd /opt/telegram-card-platform
sudo bash deploy/cloud/install.sh
sudo nano /opt/telegram-card-platform/.env
sudo systemctl start telegram-card-platform
```

新服务器 `.env` 必须保持：

```env
REMOTE_OCR_ENABLED=false
REMOTE_OCR_URL=
```

详细步骤见 [DEPLOY.md](DEPLOY.md)。

## Owner Hybrid / RTX5070

先执行完全相同的 Cloud Deploy 安装，再仅在私有 `.env` 中配置自己的 Worker：

```env
REMOTE_OCR_ENABLED=true
REMOTE_OCR_URL=http://YOUR_PRIVATE_WORKER:8000
```

不要将真实地址、Tailscale 信息或任何密钥提交到 Git。详细流程见 [docs/OWNER_HYBRID_DEPLOY.md](docs/OWNER_HYBRID_DEPLOY.md)。

## 更新、日志与健康检查

```bash
cd /opt/telegram-card-platform
sudo bash deploy/cloud/update.sh
sudo bash deploy/cloud/health.sh
journalctl -u telegram-card-platform -f
```

## 备份与回滚

```bash
bash scripts/backup_data.sh
```

部署前备份优先于 Git 回滚。完整说明见 [ROLLBACK.md](ROLLBACK.md)。

## 验证

```bash
python -m pytest
python -m compileall -q bot.py config handlers services storage utils tests
python scripts/check_deploy_consistency.py
```

私有图片、OCR 审计原图、运行输出、数据库、日志和 `.env` 都被忽略，禁止上传到 GitHub。
