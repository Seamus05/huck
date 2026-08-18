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
│   ├── opencode.json   # committed agent definition — the seed carries its own identity
│   └── tools/
│       └── query-memory.ts # Huck's read tool: search shared Mnemosyne memory
├── config/
│   ├── huck-check.service   # systemd service for drift scanner
│   ├── huck-check.timer     # 5-minute wake interval
│   └── huck-check-wrapper.sh# runs check.py, wakes Huck on drift (exit 1)
├── notebooks/
│   ├── ds.py           # chronicle() + query() + learn() + roundtrip() + resolved-ledger helpers
│   ├── check.py        # drift scanner — tests, tree, agent seed, unresolved, tracker, dashboard
│   ├── verify_loop.py  # loop proof CLI — write → read → match, saves state/loop-proof.json
│   ├── test_ds.py      # unit tests for ds.py
│   ├── test_check.py   # unit tests for check.py dashboard + tracker + unresolved filter
│   ├── test_verify_loop.py # unit tests for verify_loop.py
│   └── test_query_memory.ts # bun tests for .opencode/tools/query-memory.ts
├── chronicles/         # committed session chronicles (the durable record)
│   ├── 2026-08-18-loop-proof.md  # the loop-proof build chronicle
│   ├── 2026-08-18-cross-session.md # cross-session continuity build chronicle
│   └── 2026-08-18-where-i-am.md  # position chronicle — clean-check bearing, next slice named
├── prompts/            # experiment/task prompts given to Huck
│   ├── build-query-tool.md  # the query-tool experiment brief
│   └── fresh-workspace-start.md # the isolated-worktree start brief (this build)
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

## Cross-session continuity — resolution state travels with the agent

The next acceptance criterion, proved from a fresh isolated worktree
(branch `b1-memory-loop`, 2026-08-18): a new checkout must reach the same
"what's done" conclusion as the checkout that did the work. Before this
build, `state/resolved.json` was the only resolution ledger — gitignored,
so a fresh checkout forgot everything. The worktree's own check exposed it
live: 2 items that the main checkout had already resolved were flagged as
unresolved.

Two layers of fix:

1. **The resolution ledger lives in shared memory too.** `mark_resolved()`
   chronicles a resolution record to Mnemosyne (metadata keyed by
   `huck/state/resolved.json` + `resolved_id`); `resolved_ids()` merges the
   local file with the memory ledger. A fresh checkout with no `state/` dir
   still knows what prior sessions resolved — knowledge crosses checkout
   boundaries through the same Mnemosyne layer the loop proof verifies.
   Falsifiable pass condition: fresh checkout, no local state → `check.py`
   reports the same resolved set as the originating checkout.
2. **`built ` is a past-tense completion opener.** The drift filter
   recognised "Created X", "Implemented Y" as records of work done — but
   deliberately excluded "built ", so "Built the learn() bridge" (a
   completion chronicle) was misread as a seed. "build " (imperative) is a
   seed; "built " (past) is a record. The trailing 't' distinguishes them.

Also hardened along the way:

- **`ds.passage_metadata()`** — the Mnemosyne service returns metadata as
  `metadata_` (a JSON string), not `metadata` (a dict). The read path was
  blind to its own resolution records, and check.py's `source_file` filter
  had silently stopped matching real passages. One normalizer fixes both.
- **`check_agent_config()`** — the repo's committed `.opencode/opencode.json`
  must still define `agent.huck`, or the check flags drift. The agent
  definition travels with the repo because the seed must be able to
  instantiate itself: an agent that needs ambient global config to exist
  isn't independent, it's dependent.
- **Loop proof re-verified from the worktree** — `verify_loop.py` returns
  `LOOP VERIFIED` from the fresh checkout, evidence in the worktree's own
  `state/loop-proof.json`.

Known worktree gap (noted, not fixed): `.opencode/node_modules` is
gitignored, so the bun tests for `query-memory.ts` can't run in a fresh
worktree without a reinstall. The tool file travels; its test deps don't.
The python suite (78 tests) runs clean from a bare checkout.
