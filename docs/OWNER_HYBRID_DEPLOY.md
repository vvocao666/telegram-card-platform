# Owner Hybrid / RTX5070 部署

Owner Hybrid 与 Cloud Deploy 使用同一个 `main` commit、同一套 `bot.py`、`handlers`、`services`、`storage` 与数据库结构。唯一差异是 Owner Hybrid 在云端 `.env` 中启用可选的 Remote OCR。

## 云端机器人

先按 [Cloud Deploy](../DEPLOY.md) 安装。随后仅在私有 `.env` 中设置：

```env
REMOTE_OCR_ENABLED=true
REMOTE_OCR_URL=http://YOUR_PRIVATE_WORKER:8000
```

Remote Worker 不可达、超时或未返回有效卡密时，机器人会自动回退 OCR.space；不要把真实私有地址、Token 或 Tailscale 密钥提交到 Git。

## Windows RTX5070 Worker

Worker 源码位于 `workers/rtx5070/`，运行目录可复制到 Windows 主机。Worker 保持 PaddleX 模型常驻，GPU 推理串行，`/health` 与 `/ocr` 接口供云端机器人使用。

运行前确认：

```powershell
Get-Service RTX5070_OCR
Invoke-WebRequest http://127.0.0.1:8000/health
```

使用 `scripts/windows_install_ocr_autostart.ps1` 安装开机自启服务。关闭显示器不影响 Worker；计算机进入睡眠或关机时 Worker 不可达，云端将自动使用 OCR.space。

## 健康检查

在 Telegram 中使用 owner 状态命令，或在云端运行：

```bash
systemctl status telegram-card-platform --no-pager
journalctl -u telegram-card-platform -n 100 --no-pager
```
