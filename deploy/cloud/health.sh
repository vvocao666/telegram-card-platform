#!/usr/bin/env bash
set -euo pipefail

systemctl is-active telegram-card-platform
systemctl status telegram-card-platform --no-pager
journalctl -u telegram-card-platform -n 100 --no-pager
