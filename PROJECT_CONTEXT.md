# Telegram Card Platform 项目长期上下文

> 以后处理本项目时，必须先阅读本文件，再检查当前 Git、测试和生产状态。
> 本文件记录不可遗漏的业务事实和安全边界，不保存 Token、API Key、真实 `.env`、数据库内容或私人服务器凭据。

## 1. 当前基线

- 项目名称：`telegram-card-platform`
- GitHub：`https://github.com/vvocao666/telegram-card-platform`
- 标准分支：`main`
- 当前最佳版本：当前生产机器人。它是后续所有工作的黄金基线，不允许未经验证直接替换。
- 本次架构整理前本地与 `origin/main` 一致，生产黄金基线 commit：`33a3336`
- 本次记录时工作区干净。
- 生产目录：`/opt/telegram-card-platform`
- systemd 服务：`telegram-card-platform`
- Windows OCR Worker 目录：`D:\gpu_ocr`
- Windows OCR 服务：`RTX5070_OCR`

以上 commit、服务状态和线上目录内容属于易变化信息。每次工作开始必须重新执行 Git、SSH 和 systemd 检查，不能只相信本文档。

## 2. 永久版本关系

### Cloud Deploy

`main` 是唯一标准的 Cloud Deploy 滚动版本，必须包含当前所有通用业务功能、Bug 修复、OCR 规则、记账、广播、通知、状态、学习、排序和去重功能。

默认配置：

```env
REMOTE_OCR_ENABLED=false
REMOTE_OCR_URL=
```

普通 Ubuntu 云服务器部署后不能依赖 Windows、RTX5070、Tailscale 或私人地址。

### owner-hybrid

固定关系：

```text
owner-hybrid = Cloud Deploy + RTX5070 + Windows OCR Worker + Tailscale/Remote OCR 环境配置
```

owner-hybrid 不能拥有 Cloud Deploy 缺失的业务功能。它只通过 `.env` 开启本地 GPU 增强，不维护另一套业务代码。

## 3. 工作原则

每次收到优化需求后，先向用户说明：

1. 准备怎么做。
2. 完成后会是什么效果。
3. 是否影响其他功能。
4. 如何测试和回滚。

实施限制：

- 当前功能已基本完善，优先修复和优化，不继续堆叠功能。
- 不改变现有用户操作习惯、回复格式和业务规则，除非用户明确要求。
- 不猜卡、不补造字符、不从不相邻文本拼卡。
- 宁可进入复核或备用 OCR，也不能输出无法追溯的假卡。
- 修改前检查本地、GitHub、生产差异。
- 部署前必须备份项目、`.env` 和 `ledger.sqlite3`。
- 不使用 `git reset --hard`、`git clean` 或强制覆盖生产有效修改。
- 小修复只 commit/push `main`，不创建 Tag 或 Release，除非用户明确要求。
- 不泄露任何 Token、Key、数据库内容、owner ID 或私人地址。

## 4. 当前架构

```text
bot.py                  启动、Application 创建和 handler 注册
config/application.py   唯一的 Telegram Application 构建入口
config/                 配置、日志、常量
handlers/registry.py    唯一的生产 handler 注册表与顺序契约
handlers/               Telegram Update 接入层
services/ocr/           OCR、候选、校验、纠错、学习、字体和缓存
services/ocr/command_service.py OCR 管理与显式学习命令编排
services/ocr/provider_router.py  Remote 状态、熔断和 provider 统计计算
services/ocr/batch_processor.py  OCR 批次进度与稳定排序
services/ocr/result_pipeline.py  最终卡密排序、去重和回复格式管线
services/ledger/        记账业务
services/broadcast/     owner 私聊群组广播流程
services/notify/        当前群成员通知流程
services/forward/       转发服务
services/price/         价格查询
services/trc20/         TRC20 地址校验
services/background_tasks.py 后台任务启动、去重和关闭
services/file_cleanup.py     临时图片与审计文件安全清理
services/runtime.py     兼容层和主要运行时编排
storage/                数据库、模型和 repositories
tests/                  回归测试、真实案例和 benchmark
scripts/                备份、部署和恢复
systemd/                Linux 服务与定时备份
feature_backups/        历史稳定备份
```

`services/runtime.py` 多轮行为保持型拆分后约 2789 行，仍是当前最大维护风险。本轮已把 Remote OCR、OCR.space 和 provider 路由编排迁入 `services/ocr/remote_provider.py`、`services/ocr/ocrspace_provider.py`、`services/ocr/provider_orchestration.py`，`runtime.py` 只保留兼容委托入口。生产 handler 注册、Application 构建、后台任务生命周期、文件清理、广播与通知、状态、价格、群组、TRC20、审计、OCR 管理命令、图片顺序和限流也已迁出。以后继续逐步拆分编排职责，但必须先锁定测试，采用兼容委托和小步接管方式，不能整体重写或改变行为。

永久约束：后续优化不得继续向 `services/runtime.py` 或 Windows Worker 的 `server.py` 堆积算法和业务实现。`runtime.py` 只保留兼容入口与编排，`server.py` 只保留 FastAPI 接口与调度；新增算法必须进入职责明确、可独立测试的小模块。

批量图片默认不设硬数量上限（`PHOTO_BATCH_MAX_IMAGES=0`），所有已接收图片都进入队列；实际下载与 OCR 工作始终受 `OCR_CONCURRENCY` 限制，禁止以无限并发换速度，也禁止静默丢弃超过固定张数的图片。

真实图片基准入口为 `scripts/run_ocr_image_benchmark.py`，清单格式见 `benchmarks/ocr/README.md`。人工真值图片必须放在被 Git 忽略的 `benchmarks/ocr/private/`，不得上传用户图片或把 OCR 自身输出冒充 Ground Truth。基准必须同时统计精确匹配、漏识别、误识别、类型串类、顺序、p50 和 p95。

每日视觉审计可通过 `services/ocr/adaptive_optimizer.py` 聚合图片字体、版式、清晰度与失败类型，只生成影子 `secondary_verification` 候选。候选不得自动改代码、自动部署或生成全局字符替换；只有同一套真实 benchmark 显示精确匹配增加，且漏识别、误识别、串类、顺序均不退化时，才允许人工批准后另行接入。

## 5. 当前功能边界

主项目是卡密识别机器人，同时保留完整记账功能。不要因为存在独立 `telegram-ledger-bot` 仓库而删除或弱化本项目记账功能。

当前主要能力：

- Telegram 图片、相册和图片文件 OCR。
- PUBG / PSN 图片级互斥分类。
- RTX5070 Remote OCR 与 OCR.space 自动 fallback。
- OpenCV 轻量预处理。
- 多图并发、进度提示和按发送顺序统一输出。
- 卡密引用格式输出，单条和多条保持一致。
- 今日 OCR 缓存、学习、字体模板、审计和复核统计。
- 每天北京时间 00:00 向 owner 汇总上一自然日各群、各用户的图片数和 PUBG/PSN 卡密数。
- 群内 `/统计` 按用户汇总当前群北京时间当天的图片数和已识别 PUBG/PSN 卡密数；`/统计` 统计 00:00 至命令发送时间，`/统计12:01` 统计 12:01 至命令发送时间，`/统计12:00-18:00` 统计指定区间。图片归属以 Telegram 原消息时间为准，不以 OCR 完成时间为准；仅排除全局机器人 owner，其他用户正常统计；重复卡密在所选区间内保留第一次出现并只计一次，重复图片仍计入发送图片数。
- 稳定去重、疑似重复提醒。
- 记账、汇率、费率、日切、价格查询和账单。
- owner 私聊群组广播。
- 当前群通知所有人。
- 状态面板和 OCR 调试命令。
- `/上课`、`/下课` 群状态控制。
- TRC20 地址防篡改/校验模块。
- systemd、一键部署、备份和恢复。

双向私聊中继代码仍保留在仓库，但当前 `bot.py` 没有注册该 handler，属于关闭状态。不要在没有用户明确要求时重新启用。

## 6. OCR 路由

owner-hybrid 的目标顺序：

```text
RTX5070 在线 -> 使用 Remote OCR
RTX5070 首次失败/超时/无有效卡 -> 立即使用 OCR.space
Remote 离线冷却期 -> 当前批次后续图片跳过 Remote，直接 OCR.space
冷却结束 -> 再探测 Remote
```

当前默认参数：

- `OCR_CONCURRENCY=20`
- `REMOTE_OCR_OFFLINE_SECONDS=180`
- Remote 健康检查应短时缓存，不能每张图片重复等待。
- Remote 成功并返回有效卡后，不再调用 OCR.space。
- Worker 原图/增强图返回的同一卡密文本按卡锚点去重计数，不能因重复 `S07` 行误触发 OCR.space。
- 不同卡锚点仍分别计数；检测数量大于有效结果数量时必须继续补识别。
- Remote 失败、超时、非法 JSON 或无有效卡时才 fallback。
- 相同图片保留哈希缓存，避免重复上传和重复 OCR。
- OCR.space 并发不能破坏 Telegram 图片接收顺序。

本地 Windows Worker 当前模型：

- 可复制源已纳入 `workers/rtx5070/`，用于版本审计、测试和新机器复现。
- 实际运行目录仍为 `D:\gpu_ocr`；部署时从仓库复制，不在生产云服务器安装 GPU 依赖。

- `PP-OCRv6_medium_det`
- `PP-OCRv6_medium_rec`
- PaddleX OCR pipeline 常驻 GPU。
- GPU 推理保持串行安全；OpenCV 在 CPU 执行。
- 关闭显示器不影响服务；电脑不能睡眠或休眠，否则 Remote OCR 离线。

## 7. PUBG 业务真值

### 格式

PUBG 前缀不是固定白名单。只要满足 `S07` 开头并跟随 3 位数字，就是 PUBG 前缀：

```text
S07[0-9]{3}
```

当前接受的完整结构：

```text
S07xxx-XXXX-XXXX-XXXX
S07xxx-XXXX-XXXX-XXXXX
```

其中 `x` 是前缀数字，正文 `X` 是大写字母或数字。

关键规则：

- 第一位必须是 `S`。
- 第二位必须是 `0`。
- `S07` 后必须再有 3 位数字，构成 6 位前缀。
- 图片中出现明确或疑似 `S07` 痕迹时，优先判定为 PUBG 图片。
- PUBG 图片禁止输出 PSN，即使 PUBG 暂时提取失败也不能从后半段派生 PSN。
- 一张图片只允许一种卡密类型。

### 当前强制重识别规则

对所有 `S07` PUBG 卡密，不只针对 `S07336`：如果后三段正文出现 `0`、`1`、`O` 或 `I`，当前业务规则视为错误候选，必须丢弃并触发备用 OCR/复核，不能直接输出。

日志：

```text
OCR RESULT DROPPED reason=pubg_forbidden_body_chars
```

### 换行拼接

- 优先使用 OCR `rec_boxes` / `rec_polys` 坐标。
- 图片内先按 `y` 从上到下，同一行按 `x` 从左到右。
- 没有坐标时才使用 OCR 原始返回顺序。
- 发现 `S07` 开头但不完整的行，只能向下尝试紧邻的 1-3 行。
- 按实际缺失位数补齐。
- 下一段超过缺失位数时不能硬截断拼接，应标记 unresolved。
- 拼接结果必须通过完整 PUBG 格式验证。
- 如果 texts 相邻行重建结果与 worker cards 冲突，优先使用可追溯的 texts 重建结果。
- 禁止从下一张卡、按钮文字、密码、长号码或其他不相邻文本补卡。

## 8. PSN 业务真值

PSN 格式：

```text
XXXX-XXXX-XXXX
```

规则：

- 只在非 PUBG 图片中提取 PSN。
- PSN 必须是独立 token。
- 如果 PSN 是更长乱码 token 或 PUBG 卡密的子串，必须丢弃并触发备用 OCR/复核。
- 禁止从 PUBG 后三段截取 PSN。

## 9. 纠错安全边界

- 禁止全局无条件 `2 -> Z`、`J -> U` 或其他字符替换。
- 禁止用历史完整卡密或历史精确卡段改写未来卡密；卡密均为一次性数据。
- 学习规则必须绑定字体、错误字符、正确字符、位置和上下文。
- 字体不匹配、置信度不足或格式不合法时不能自动纠错。
- 正常清晰且完整合法的结果不应被学习层改写。
- 不确定结果标记 `needs_review`，不能为了提高识别数量输出假卡。
- 人工真值优先于 OCR，但人工真值不能被 OCR 反向覆盖。

当前 `/learn_cards` 和“学习卡密”流程保留用于人工真值审计、统计和字体特征样本，不得生成可自动复用的完整卡密映射。

字符级泛化必须满足真实字体哈希完全匹配、同位置、同上下文、重复次数阈值和 Validator 校验。`unknown_font`、旧完整卡密映射和旧精确卡段不得参与自动纠错。不得在线直接修改生产模型权重。

## 10. 输出顺序和去重

- 图片进入队列时立即分配递增 `sequence_index`。
- `sequence_index` 来自 Telegram Update 接收顺序，不来自 OCR 完成顺序。
- 最终顺序：`sequence_index ASC`、`y ASC`、`x ASC`。
- OCR 可以并发完成，但输出必须等待排序后统一生成。
- 去重使用 `canonical_card`，保留第一次出现的位置。
- 禁止使用按卡密文本排序、`set()` 或 `list(set())` 打乱顺序。
- 单张图片内相同卡密只保留一次。
- 不增加图片编号，不改变现有回复样式，除非用户明确要求。

## 11. 文本和权限

- 普通文本消息即使包含卡密，也不能触发 OCR 结果回复。
- 图片、照片、图片文件和相册才进入 OCR。
- owner 学习命令仍然可以处理人工卡密文本。
- 学习、字体管理、状态和敏感管理操作必须执行 owner/admin 权限检查。
- 群内学习纠错只有 owner 有权限。

`/上课`、`/下课`：

- owner 私聊命令作用于所有已记录群，命令本身静默。
- 群内命令只作用当前群，并沿用现有管理权限。
- 每个群在后续第一条非命令消息时只提示一次。
- `/下课` 关闭卡密识别，`/上课` 恢复识别。

## 12. 缓存、学习和审计

- 今日 OCR 缓存：`outputs/today_ocr_cache.json`
- 缓存按当天追加、稳定去重，不应覆盖同日旧数据。
- 日常状态统计必须读取真实当天缓存，不能累计历史图片造成虚高。
- 人工学习时缓存不存在，禁止把人工卡密全部统计为漏识别。
- 学习比对：正确为 OCR 与人工交集，遗漏为人工减 OCR，多识别为 OCR 减人工。
- OCR 审计功能是项目关键功能，必须保留原始文本、候选、拒绝原因、最佳候选、评分和来源。
- 字体模板、学习规则和报告存放在 `outputs/`，部署时不得清空。

## 13. 记账功能不可遗漏

主项目必须继续保留：

- 群级汇率、费率和日切。
- 汇率/费率快照。
- 手续费、应下发人民币和 U。
- 今日、昨日和完整账单。
- 入款、下发、撤销、清空和权限。
- 裸负数（如 `-100`）是减分（入款冲减），计入入款及应下发金额，显示在“减分”栏，绝不记入“已下发”；只有以“下发”开头的明确指令（如 `下发100`、`下发-200`）才创建下发流水，`/out`、`/payout`、`出款`、`下分`均不触发下发。
- 账单顶部的入款、下发明细优先显示回复对象或手工备注；没有回复和备注时显示实际发送记账命令者的昵称。最近流水保持简洁格式。
- OKX/欧意价格查询与“设置实时汇率”分离。
- 历史账单不能因新设置重新计算。
- `ledger.sqlite3` 不能删除、清空或被测试覆盖。

本项目中的记账调整以当前卡密识别生产机器人为准。独立记账机器人是另一个项目，不得混淆路径、仓库或部署目标。

## 14. 部署和回滚

部署前：

1. 检查 `git status`、当前分支、commit 和远程。
2. 检查生产未提交修改并判断是否为有效线上修复。
3. 创建带时间戳的生产备份。
4. 单独备份 `.env`、`ledger.sqlite3`、`outputs/` 和 systemd service。
5. 本地运行完整测试和 compileall。
6. 不覆盖生产 `.env`、数据库和 `outputs/`。

验证命令：

```bash
python -m pytest
python -m compileall -q bot.py config handlers services storage utils tests
```

生产检查：

```bash
systemctl status telegram-card-platform --no-pager
journalctl -u telegram-card-platform -n 100 --no-pager
```

失败时：

- 立即停止新服务。
- 从本次部署前备份恢复代码和 service。
- 保留当前 `.env`、数据库和输出数据。
- 启动旧服务并检查日志。

## 15. 测试要求

任何 OCR 修改至少验证：

- 正常清晰 PUBG。
- 正常清晰 PSN。
- 任意 `S07xxx` 前缀。
- PUBG 四位和五位尾段。
- 多卡图片不遗漏。
- 相邻行换行拼接。
- 禁止跨卡、跨行乱拼。
- PUBG/PSN 图片级互斥。
- OCR 完成顺序打乱时输出顺序不变。
- 去重保留第一次出现位置。
- Remote 在线和离线 fallback。
- 普通文本不触发 OCR。
- 历史真实错误案例。

任何改动都必须运行完整 pytest 和 compileall。不能只运行新增测试后直接部署。

## 16. 当前最佳版本保护

当前机器人被用户确认为目前最好的版本。后续优化必须遵循：

```text
当前生产结果作为 A 组
新实现作为 B 组
离线真实样本对比
无准确率、遗漏率、顺序或延迟回归
小范围灰度
确认后部署
随时可切回 A 组
```

不得因为“模型更新”“规则更智能”或“代码更整洁”直接替换已经稳定工作的路径。

## 17. 每次开始工作的快速检查

```bash
git status --short --branch
git log -5 --oneline --decorate
git remote -v
git diff origin/main...HEAD
```

随后检查：

- 生产 commit 和 `git status`。
- systemd 服务状态和最近日志。
- `.env` 只检查变量是否存在，不输出值。
- Windows Worker `/health` 与服务状态（仅 owner-hybrid）。
- 最近真实失败图片对应的 OCR raw texts、坐标、候选和拒绝原因。

## 18. 本文件维护规则

- 只有已经实现、测试或用户明确确认的事实才能写入“当前功能”。
- 尚未实现的想法必须标记为“讨论中”。
- 每次重大行为变更后同步更新本文件。
- 不记录密钥、Token、数据库内容、真实用户信息或私人网络地址。
- 易变化的 commit、测试数量和服务状态必须注明核验时间，不能长期当作固定事实。
