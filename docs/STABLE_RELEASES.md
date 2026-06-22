# Stable Releases

## Recommended Versions

### Ordinary Cloud Server Deployment

Use:

```text
v1.3.0-ocr-learning-plus
```

Label: Cloud Stable / 通用云服务器稳定版 / 最后通用稳定版

This release is the last general cloud-server stable version before local RTX5070 Hybrid OCR was introduced.

Included:

- Telegram card recognition.
- OCR.space / original OCR flow.
- Ledger/accounting.
- Duplicate detection.
- Output ordering.
- OCR learning.
- OCR review and font-related enhancements.
- Direct deployment to ordinary Ubuntu/Debian cloud servers.

Not included:

- RTX5070.
- Windows OCR Worker.
- Tailscale.
- Remote OCR API.
- Hybrid OCR.
- Local GPU acceleration.

### Owner RTX5070 Deployment

Use the current `v2.x` release line only for the owner environment.

The `v2.x` releases include owner-specific Hybrid OCR features:

- Windows RTX5070 OCR Worker.
- Tailscale network routing.
- `REMOTE_OCR_URL`.
- Hybrid OCR routing.
- Local GPU-first OCR.

These releases are not recommended for ordinary cloud-only deployments.

## Why v1.3.0 Is The General Stable Baseline

`v1.3.0-ocr-learning-plus` is the final stable version before `v2.0.0-hybrid-ocr` introduced Remote OCR and owner-specific GPU infrastructure.

For a normal new deployment, start from:

```bash
git checkout v1.3.0-ocr-learning-plus
```

For the owner production environment, continue using the current `v2.x` release.
