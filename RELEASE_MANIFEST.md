# 生产封版清单

- 发布日期：2026-07-14
- 正式代码源：`main`
- 完整 Commit SHA：由 `production-cloud-2026.07.14` 与 `production-owner-hybrid-2026.07.14` 两个标签解析；两者必须指向同一提交，发布报告记录完整 SHA。
- 测试：封版时执行 `python -m pytest`
- 编译检查：封版时执行 `python -m compileall -q bot.py config handlers services storage utils tests`
- Cloud Deploy 入口：`deploy/cloud/install.sh`、`deploy/cloud/update.sh`
- Owner Hybrid 入口：`deploy/owner-hybrid/install.sh`、`docs/OWNER_HYBRID_DEPLOY.md`

## 一致性承诺

Cloud Deploy 与 Owner Hybrid 使用完全相同的 `bot.py`、`config`、`handlers`、`services`、`storage` 和 `utils`。差异仅限 `.env` 示例、部署说明和 Windows RTX5070 Worker 的启动方式。

## 已知限制

- Cloud Deploy 默认关闭 Remote OCR，使用 OCR.space 与现有安全回退路径。
- Owner Hybrid 的 Windows Worker 在睡眠或关机时不可达，云端自动回退 OCR.space。
- OCR 无法确认的图片进入复核；系统不猜测或补造卡密。

## 回滚

优先恢复生产部署前备份；详细步骤见 [ROLLBACK.md](ROLLBACK.md)。
