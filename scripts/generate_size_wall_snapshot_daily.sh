#!/usr/bin/env bash
set -euo pipefail

cd /srv/huabang-ai-center/backend
export PYTHONPATH=.
exec .venv/bin/python scripts/generate_size_wall_snapshot.py
