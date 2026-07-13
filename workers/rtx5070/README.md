# RTX5070 OCR Worker

该目录是当前 owner-hybrid Windows OCR Worker 的可审计源码副本。云服务器版默认不启用，也不依赖这里的组件。

## 接口兼容

- `GET /health`
- `POST /ocr`，multipart 字段名为 `file`
- 返回继续保留 `ok`、`cards`、`texts`、`enhanced_used`、`cached` 等字段

## 同步到工作目录

生产 Worker 仍运行在 `D:\gpu_ocr`。更新前先停止 `RTX5070_OCR` 服务并备份该目录，然后复制本目录中的 Python 文件和服务脚本。不要复制主项目 `.env`、Token 或任何服务器地址。

## 安装

1. 创建 `D:\gpu_ocr\venv`。
2. 根据 RTX5070 驱动和 CUDA 版本安装匹配的 `paddlepaddle-gpu`。
3. 安装 `requirements.txt`。
4. 运行 `install_service.ps1`。
5. 使用 `status_service.ps1` 和 `http://127.0.0.1:8000/health` 验证。

模型在进程启动时加载一次，GPU 推理继续使用串行信号量；OpenCV 仅在需要时走 CPU 增强。
