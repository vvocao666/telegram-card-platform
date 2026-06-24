# 稳定版本说明

## 当前推荐

普通云服务器部署：

```text
v2.8.0-cloud-deploy
```

我本人 RTX5070 专用：

```text
owner-hybrid 最新版
```

旧稳定版：

```text
v1.3.0-ocr-learning-plus
```

`v1.3.0-ocr-learning-plus` 已归档，不再作为最新推荐部署版本。

## v2.8.0-cloud-deploy

这是当前最新版功能整理出的通用云服务器部署版。

适合：

- 普通 Ubuntu / Debian 云服务器
- 只配置 Telegram Bot Token 和 OCR.space Key
- 不运行本地 Windows GPU
- 不使用 Tailscale

包含：

- Telegram 卡密识别
- OCR.space / 云端 OCR
- PUBG/PSN 图片级互斥
- 任意 `S07XXX-XXXX-XXXX-XXXXX` 识别为 PUBG
- PUBG 换行拼接
- 文本消息不重复提取卡密
- 去重、排序、Validator
- OCR 学习功能
- 状态面板
- 记账、广播、管理员权限
- 今日统计和缓存逻辑

默认不依赖：

- RTX5070
- Windows OCR Worker
- Tailscale
- Remote OCR API
- Hybrid OCR
- 本地显卡加速

## owner-hybrid 版本

owner-hybrid 是我本人生产环境专用版本。

适合：

- 阿里云机器人
- Windows RTX5070 OCR Worker
- Tailscale 打通
- `REMOTE_OCR_ENABLED=true`
- `REMOTE_OCR_URL=http://100.81.208.104:8000`

普通云服务器不要默认部署 owner-hybrid。

## 历史版本

### v1.3.0-ocr-learning-plus

历史通用稳定版，已经归档。

它不包含 RTX5070 / Remote OCR / Hybrid OCR，但也缺少后续修复：

- 新的 PUBG/PSN 分类修复
- 任意 S07 前缀修复
- 文本消息忽略修复
- 状态面板增强
- 后续 OCR 排序和缓存修复

因此不再作为最新推荐部署版本。
