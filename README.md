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
│   ├── ds.py           # chronicle() + query() + learn() + roundtrip() helpers for Mnemosyne
│   ├── check.py        # drift scanner — tests, tree, unresolved items, tracker, dashboard
│   ├── verify_loop.py  # loop proof CLI — write → read → match, saves state/loop-proof.json
│   ├── test_ds.py      # unit tests for ds.py
│   ├── test_check.py   # unit tests for check.py dashboard + tracker + unresolved filter
│   ├── test_verify_loop.py # unit tests for verify_loop.py
│   └── test_query_memory.ts # bun tests for .opencode/tools/query-memory.ts
├── chronicles/         # committed session chronicles (the durable record)
│   └── 2026-08-18-loop-proof.md # the loop-proof build chronicle
├── prompts/            # experiment/task prompts given to Huck
│   └── build-query-tool.md  # the query-tool experiment brief (this build)
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
   write. Run its tests with `bun test ./notebooks/test_query_memory.ts`.

## Loop proof — the isolated agent verifies itself

The pattern's core claim: an isolated agent can record state to shared memory
and retrieve it again — write → read → match. Huck can now prove that claim
on demand:

- `ds.roundtrip()` — writes a unique marker passage to Mnemosyne, queries it
  back through the real semantic-search path, and verifies the SAME passage
  id comes back. Returns an evidence dict.
- `python3 notebooks/verify_loop.py` — the deliberate, human-visible proof:
  runs the round-trip, prints `LOOP VERIFIED`, and saves machine-readable
  evidence to `state/loop-proof.json` (git-ignored). Exit 0 on a match.
  `--no-save` prints without writing; `--tag <name>` customises the marker.
  NOT timer-driven — every run leaves one marker passage in the archive.
- **Read probe in check.py** — `check_mnemosyne()` no longer trusts `/health`
  alone: it also issues a write-free read query (`tracked=false`) so the
  5-minute check proves the read loop, not just that the service answers.
  A loop that can write but not read is a broken pattern.
- **Unresolved filter hardened** — the drift scanner now recognises
  completion chronicles by text structure (`## Episode:`, `### Approach`,
  past-tense openings) as well as tags, so records of work done don't wake
  Huck as false drift.

This addresses the tracker's open question — acceptance criteria for
"proving the pattern" — at the memory layer: end-to-end independence means
the agent can verify its own loop and produce evidence, no orchestrator
required.
