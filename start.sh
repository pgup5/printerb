#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ ! -x .venv/bin/python ]]; then
    echo 'Missing Linux environment. Follow the Linux Mint setup in README.md first.' >&2
    exit 1
fi
exec .venv/bin/python main.py "$@"
