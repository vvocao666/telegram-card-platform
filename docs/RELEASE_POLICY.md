# 发布规则

## 日常维护

小 Bug、OCR 规则修复、性能优化、文档修改和管理员功能修复只提交并推送 `main`：

```bash
git commit -m "描述本次维护内容"
git push origin main
```

不创建 Tag 或 GitHub Release。

## 正式封版

仅在 OCR 引擎变更、数据库结构变更、部署方式变更、重大架构升级或长期稳定版封版时创建 Tag / Release。

正式封版必须：

1. 生产、本地和 `origin/main` 位于同一 commit。
2. 完整 pytest、compileall、部署一致性检查全部通过。
3. 备份 `.env`、数据库、`outputs/` 与 systemd service。
4. Cloud Deploy 与 Owner Hybrid 使用同一个 commit SHA。
5. 不上传 `.env`、真实地址、Token、数据库、审计原图、日志、缓存或备份。
