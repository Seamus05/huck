#!/bin/bash
# huck-check-wrapper — runs check.py, wakes Huck on drift or unresolved items
set -e

cd /home/theyokel/huck
python3 notebooks/check.py
EXIT=$?

if [ $EXIT -eq 1 ]; then
    # Drift or unresolved items found — wake Huck
    /home/theyokel/.local/bin/opencode run --agent huck --model opencode/deepseek-v4-flash \
        "check.py found drift or unresolved items. Read state/check.json, query Mnemosyne for context, and address what you find. Chronicle when done." &
fi

exit $EXIT
