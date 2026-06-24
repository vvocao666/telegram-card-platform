# 发布规范

## 目标

减少无意义 Release，避免每个小 bug 都生成正式版本。`main` 保持可用，Release 只用于明确可部署的稳定节点。

## 什么时候不创建 Release

小 bug 修复只提交到 `main`，不创建 Release。

例如：

- 单个测试修复
- 文档错字
- 单条 OCR 规则微调
- 日志字段补充
- 不影响部署的小改动

## 什么时候创建 Release

只有以下情况才创建 Release：

- 大功能完成
- 稳定版确认
- 可部署版本更新
- 重要 bug 批量修复完成
- 需要给服务器或其他人明确部署的版本

## 命名规则

### cloud-deploy

通用云服务器部署版。

特点：

- 默认 `REMOTE_OCR_ENABLED=false`
- 不依赖 RTX5070
- 不依赖 Windows OCR Worker
- 不依赖 Tailscale
- 适合普通 Ubuntu / Debian 云服务器

示例：

```text
v2.8.0-cloud-deploy
```

### owner-hybrid

我本人 RTX5070 专用版。

特点：

- 可开启 `REMOTE_OCR_ENABLED=true`
- 可配置 `REMOTE_OCR_URL`
- 使用 Windows RTX5070 OCR Worker
- 使用 Tailscale

示例：

```text
v2.8.x-owner-hybrid
```

### hotfix

紧急修复版。

用于线上严重问题，需要快速发布。

示例：

```text
v2.8.1-hotfix
```

### stable

长期稳定版。

用于一段时间验证后确认可长期部署的版本。

示例：

```text
v2.8.0-stable
```

## 推荐流程

1. 小 bug：直接 commit 到 `main`。
2. 连续修复多个 bug 后：统一整理为一个 Release。
3. 部署前运行：

```bash
python -m pytest
python -m compileall -q bot.py config handlers services storage utils tests
```

4. 确认文档中的推荐版本。
5. 创建 tag 和 GitHub Release。

## 当前版本线

- 通用云服务器：`v2.8.0-cloud-deploy`
- Owner RTX5070 专用：`owner-hybrid` 最新版
- 旧归档：`v1.3.0-ocr-learning-plus`
