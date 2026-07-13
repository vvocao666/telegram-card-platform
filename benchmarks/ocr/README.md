# OCR 真实图片基准

这里保存 benchmark 结构，不提交生产图片、用户名、群信息或一次性卡密。

1. 每日视觉审计把图片和确认结果保存在 `benchmarks/ocr/private/`。
2. `confirmed_match` 和 `confirmed_error` 可以进入金标准；`needs_review` 不得作为真值。
3. 使用 SHA-256 对图片去重，保存正确卡密、数量、类型和图片内顺序。
4. 运行：

```bash
python scripts/build_ocr_gold_dataset.py benchmarks/ocr/private
python scripts/run_ocr_image_benchmark.py benchmarks/ocr/private/gold/manifest.json
python scripts/build_ocr_adaptive_policy.py benchmarks/ocr/private
```

报告写入 `outputs/ocr_benchmark_report.json`，包含精确率、召回率、漏识别、误识别、串类、顺序错误和 p50/p95 总耗时。

真实样本至少覆盖：高清 PUBG、高清 PSN、任意 S07 前缀、换行、细长图、手写图、模糊图、多卡图、无卡图和历史串类案例。

候选自适应策略固定保持影子模式。只有真实指标不下降且精确匹配图片数增加，才允许人工批准后接入生产。
