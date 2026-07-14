# 稳定版本说明

## 当前正式生产封版

`production-cloud-2026.07.14` 与 `production-owner-hybrid-2026.07.14` 必须指向同一个 `main` commit。

- Cloud Deploy：普通 Linux 云服务器，默认 `REMOTE_OCR_ENABLED=false`。
- Owner Hybrid：同一代码源，仅在私有 `.env` 启用 RTX5070 Remote OCR。

两者拥有相同的业务功能、OCR 规则、数据库结构、审计、记账、广播、通知与管理命令。Owner Hybrid 不是独立业务分支。

## 历史版本

- `v2.8.0-cloud-deploy`：历史 Cloud Deploy 里程碑。
- `v1.3.0-ocr-learning-plus`：历史归档版本。

历史 tag 不代表当前推荐部署版本；新服务器默认部署 `main`。
