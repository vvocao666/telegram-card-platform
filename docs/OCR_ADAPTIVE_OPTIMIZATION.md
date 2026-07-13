# OCR 自适应优化

## 目标

每日审计只学习图片字体、版式、清晰度和可追溯的识别失败模式，不记忆一次性卡密，也不生成全局字符替换规则。

## 数据状态

- `confirmed_match`：图片清晰，视觉复核与机器人输出完全一致。
- `confirmed_error`：图片清晰，能够确认漏识别、误识别、串类、顺序或字符错误。
- `needs_review`：图片模糊、遮挡、多解或无法可靠确认，不参与策略学习。

## 影子策略

`services/ocr/adaptive_optimizer.py` 按稳定图片画像聚合错误率。达到以下门槛时，只生成 `secondary_verification` 候选：

- 至少 20 个已确认样本；
- 至少 3 个已确认错误；
- 待复核样本比例不超过 25%。

候选策略不会自动接管生产。它必须在同一套真实图片 benchmark 上验证：漏识别、误识别、类型串类、顺序均不得变差，精确匹配图片数必须增加，p95 延迟不得超过安全上限。

## 生成候选

```bash
python scripts/build_ocr_adaptive_policy.py benchmarks/ocr/private
```

输出为 `outputs/ocr_adaptive_policy_candidates.json`，固定使用 `mode=shadow`。只有完成独立回归和人工批准后，才允许另行接入生产路由。

确认样本先按 SHA-256 去重并生成私有金标准库：

```bash
python scripts/build_ocr_gold_dataset.py benchmarks/ocr/private
python scripts/run_ocr_image_benchmark.py benchmarks/ocr/private/gold/manifest.json
```
