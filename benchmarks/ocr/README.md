# OCR 真实图片基准

这里保存 benchmark 结构，不提交生产图片、用户名、群信息或卡密历史。

1. 将人工确认过的脱敏图片放入 `benchmarks/ocr/private/images/`。
2. 复制 `manifest.example.json` 为 `benchmarks/ocr/private/manifest.json`。
3. 每张图片填写正确卡密及图片内顺序，OCR 输出不能作为真值。
4. 运行：

```bash
python scripts/run_ocr_image_benchmark.py benchmarks/ocr/private/manifest.json
```

报告写入 `outputs/ocr_benchmark_report.json`，包含精确率、召回率、漏识别、误识别、串类、顺序错误和 p50/p95 总耗时。

建议样本至少覆盖：高清 PUBG、高清 PSN、任意 S07 前缀、换行、细长图、模糊图、多卡图、无卡图和历史串类案例。
