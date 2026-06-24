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

## 永久版本定义

### Cloud Deploy

Cloud Deploy 是唯一标准版。它永远代表当前最新、当前功能最完整、普通用户拿到源码即可直接部署的版本。

Cloud Deploy 必须同步所有通用能力：

- PUBG/PSN 识别
- OCR.space
- OCR.space fallback
- OpenCV 增强
- 缓存
- 去重
- 学习流程
- 中文“学习卡密”入口
- Validator
- 状态面板
- `/remote_ocr_status`
- Broadcast 群组广播
- Notify All 当前群 @ 活跃成员
- `/broadcast_preview`
- `/broadcast_cancel`
- `/notify_members`
- 所有管理员命令
- 所有 OCR 修复
- 所有 bug 修复
- 所有文本识别优化
- 所有排序优化
- 所有换行拼接优化
- 所有 S07 识别优化

Cloud Deploy 不允许出现“功能只在最新版 main 有”或“部署后需要手工补丁”的情况。

### owner-hybrid

owner-hybrid 是作者私人版本。

owner-hybrid = Cloud Deploy * RTX5070 本地混合识别。

只有以下能力可以只属于 owner-hybrid：

- Windows RTX5070 OCR Worker
- `REMOTE_OCR_URL`
- Tailscale
- 本地 GPU 混合识别

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
- `/remote_ocr_status`
- Broadcast 群组广播
- Notify All 当前群 @ 活跃成员
- `/broadcast_preview`
- `/broadcast_cancel`
- `/notify_members`
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

## GitHub Release 保留列表

- `v2.8.0-cloud-deploy`
- `v2.1-final-hybrid-ocr`
- `v1.3.0-ocr-learning-plus`

## GitHub Release 归档列表

除保留列表外，其余旧 Release 统一视为归档版本，命名记录为 `archive-*`。归档版本只用于历史追溯，不作为部署推荐。

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
