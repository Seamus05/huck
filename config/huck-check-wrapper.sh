#!/bin/bash
# huck-check-wrapper — runs check.py, wakes Huck on drift or unresolved items
#
# Guard: only one wake at a time. The backgrounded opencode run is wrapped in
# `flock -n`, so the lock is held for the whole run — if the check exits 1
# again 5 minutes later while a Huck is still working, the spawn is skipped
# instead of piling up processes.

cd /home/theyokel/huck
python3 notebooks/check.py
EXIT=$?

if [ $EXIT -eq 1 ]; then
    # Drift or unresolved items found — wake Huck, but only if not already awake
    nohup flock -n /tmp/huck-wake.lock -c \
        "/home/theyokel/.opencode/bin/opencode run --agent huck \
            \"check.py found drift or unresolved items. Read state/check.json, query Mnemosyne for context, and address what you find. Chronicle when done.\"" \
        >> /tmp/huck-wake.log 2>&1 &
    disown
fi

exit $EXIT