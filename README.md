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
├── .opencode/
│   └── tools/
│       └── query-memory.ts # Huck's read tool: search shared Mnemosyne memory
├── config/
│   ├── huck-check.service   # systemd service for drift scanner
│   ├── huck-check.timer     # 5-minute wake interval
│   └── huck-check-wrapper.sh# runs check.py, wakes Huck on drift (exit 1)
├── notebooks/
│   ├── ds.py           # chronicle() + query() + learn() helpers for Mnemosyne
│   ├── check.py        # drift scanner — tests, tree, unresolved items, tracker, dashboard
│   ├── test_ds.py      # unit tests for ds.py
│   ├── test_check.py   # unit tests for check.py dashboard + tracker
│   └── test_query_memory.ts # bun tests for .opencode/tools/query-memory.ts
├── prompts/            # experiment/task prompts given to Huck
├── state/              # runtime state (git-ignored): check.json, health.json, dashboard.md
└── README.md
```

## Map

Part of **Prove the Isolated-Agent Pattern (A → B → C)** — `Seamus05/Lab#1`,
Track B. Huck is the B1 answer: the agent that proves isolation works.

## Self-updating dashboard

Every check run writes:

- `state/check.json` — the structured report (fingerprint, transition tracking)
- `state/health.json` — rolling history of the last 200 checks
- `state/dashboard.md` — human-readable health dashboard with a 10-run trend

The 5-minute timer keeps all three fresh. The dashboard also surfaces open
issues from the `Seamus05/Lab#1` Wayfinder tracker (informational only —
tracker state never flips the check's exit code).

## Bridges from the growth seed

1. **Wayfinder tracker link** — `check.py` lists open `Seamus05/Lab` issues via `gh`.
2. **learn()** — `ds.py` cross-agent query that mines the whole shared corpus.
3. **Health dashboard** — self-updating dashboard in `state/` (see above).
4. **query-memory tool** — `.opencode/tools/query-memory.ts` gives Huck a
   first-class read side: semantic search across ALL Mnemosyne archives
   (the corpus is split — `default` + the agent UUID archive + smaller ones).
   Built 2026-08-18 so Huck could read what other agents chronicled, not just
   write. Run its tests with `bun test notebooks/test_query_memory.ts`.
