#!/usr/bin/env bash
set -euo pipefail

cd /srv/huabang-ai-center/backend
export PYTHONPATH=.
exec .venv/bin/python scripts/sync_baison_product_inbound.py --days 14
