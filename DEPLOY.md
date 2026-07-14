# 部署指南

支持 Ubuntu 22.04、Ubuntu 24.04、Debian 12。`main` 是唯一业务代码源；Cloud Deploy 和 Owner Hybrid 使用相同 commit SHA。

## Cloud Deploy

```bash
sudo git clone https://github.com/vvocao666/telegram-card-platform.git /opt/telegram-card-platform
cd /opt/telegram-card-platform
sudo bash deploy/cloud/install.sh
sudo nano /opt/telegram-card-platform/.env
sudo systemctl start telegram-card-platform
sudo systemctl status telegram-card-platform --no-pager
```

至少填写：

```env
BOT_TOKEN=
OCR_SPACE_API_KEY=
REMOTE_OCR_ENABLED=false
REMOTE_OCR_URL=
```

Cloud Deploy 不依赖 Windows、RTX5070、Tailscale 或 Remote OCR。Remote OCR 关闭时，机器人仍完整保留识别、记账、广播、通知、审计、状态和管理功能，并使用 OCR.space 与本地安全回退路径。

## Owner Hybrid / RTX5070

云端安装步骤与 Cloud Deploy 相同。安装完成后，仅在私有 `.env` 中填写自己的 Worker 地址：

```env
REMOTE_OCR_ENABLED=true
REMOTE_OCR_URL=http://YOUR_PRIVATE_WORKER:8000
```

Worker 离线、超时、无有效卡或返回非法数据时自动回退 OCR.space。Windows Worker 安装、自启和健康检查见 [docs/OWNER_HYBRID_DEPLOY.md](docs/OWNER_HYBRID_DEPLOY.md)。

## 更新

```bash
cd /opt/telegram-card-platform
sudo bash deploy/cloud/update.sh
```

更新脚本会在重启前备份当前项目并运行依赖安装、编译检查与测试。它不会覆盖 `.env`、`outputs/` 或 `ledger.sqlite3`。

## 运行检查

```bash
systemctl status telegram-card-platform --no-pager
journalctl -u telegram-card-platform -n 100 --no-pager
journalctl -u telegram-card-platform -f
```

## 备份与恢复

```bash
cd /opt/telegram-card-platform
bash scripts/backup_data.sh
```

恢复步骤见 [ROLLBACK.md](ROLLBACK.md)。
