# 发布规范

## 目标

减少无意义 Release，避免每个小 bug 都生成正式版本。`main` 保持可用，Release 只用于明确可部署的稳定节点。

以后不要再出现多个稳定版。Cloud Deploy 是唯一标准版，owner-hybrid 是作者私人版本。

## 永久版本定义

### Cloud Deploy

当前版本：`v2.8.0-cloud-deploy`

Cloud Deploy 永远代表当前最新、功能最完整、普通用户拿到源码即可直接部署的版本。

所有通用功能和 bug 修复默认第一时间同步进入 Cloud Deploy，包括：

- OCR 修复
- 管理员命令
- Broadcast 群组广播
- Notify All 当前群通知所有人
- 状态面板
- 文本优化
- 排序优化
- 换行拼接优化
- S07 识别优化
- 文档更新

### owner-hybrid

owner-hybrid = Cloud Deploy * RTX5070 本地混合识别。

只有以下能力允许只存在于 owner-hybrid：

- Windows RTX5070 OCR Worker
- `REMOTE_OCR_URL`
- Tailscale
- 本地 GPU 混合识别

## 什么时候不创建 Release

小 bug、OCR 修复、管理员命令、Broadcast、Notify All、状态面板、文本优化、README 更新、文档修改，只提交到 `main`，不创建 Release。

例如：

- 单个测试修复
- 文档错字
- 单条 OCR 规则微调
- 日志字段补充
- 不影响部署的小改动

## 什么时候创建 Release

只有以下情况才创建 Release：

- OCR 引擎替换
- 数据库结构变化
- 部署方式变化
- 重大重构
- 版本路线调整

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
