# 本地 CPU OCR 固定模型

CPU 第二证据使用 `rapidocr-onnxruntime==1.4.4` 内置的 PP-OCRv4 ONNX 文件，仅识别 RTX5070 已检测出的同一文本 ROI。

- 模型许可：Apache-2.0（RapidOCR 发布包）。
- 不允许运行时下载、自动升级或替换模型。
- 启动/首次使用时验证包版本及模型 SHA-256；验证失败时 CPU OCR 标记不可用，PaddleX GPU 主识别仍继续工作。
- CPU 原始文本、置信度和 ROI 坐标仅作为审计证据；不会补字符、插横杠、跨行或跨卡拼接。

模型哈希固定在 `model_registry.py`。升级必须同时更新版本、哈希、测试和人工批准记录。
