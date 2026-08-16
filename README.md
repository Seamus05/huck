# Huck

Proving agent for the isolated-agent pattern (A → B → C).

Huck is born in a VM with a seed: an identity, operating principles, a
self-sustaining work cycle, and `ds.py` (chronicle and query helpers for
Mnemosyne). A systemd timer wakes Huck every 5 minutes to scan for drift
and unresolved work. When it finds something, the fix→harden→generalise
cycle begins. When it doesn't, Huck grows.

## Layout

```
huck/
├── .gitignore
├── persona.md          # identity + operating model + self-management
├── config/
│   ├── huck-check.service   # systemd service for drift scanner
│   ├── huck-check.timer     # 5-minute wake interval
│   └── huck-check-wrapper.sh# runs check.py, wakes Huck on drift (exit 1)
├── notebooks/
│   ├── ds.py           # chronicle() + query() + learn() helpers for Mnemosyne
│   ├── check.py        # drift scanner — tests, tree, unresolved items
│   └── test_ds.py      # unit tests for ds.py
├── state/              # runtime state (git-ignored)
└── README.md
```

## Map

Part of **Prove the Isolated-Agent Pattern (A → B → C)** — `Seamus05/Lab#1`,
Track B. Huck is the B1 answer: the agent that proves isolation works.
