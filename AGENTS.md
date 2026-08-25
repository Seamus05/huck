# Huck

Proving agent for the isolated-agent pattern (A → B → C). Track B of
`Seamus05/Lab#1`.

## What this is

Huck is an agent born in a VM with a seed: an identity, operating principles,
a self-sustaining work cycle, and `ds.py` (chronicle + query helpers for
Mnemosyne). A systemd timer wakes Huck every 5 minutes to scan for drift and
unresolved work. When it finds something, the fix→harden→generalise cycle
begins. When it doesn't, Huck grows. It is not owned by a human operator.

## Layout map

```
huck/
├── persona.md          # identity + operating model + self-management
├── .opencode/
│   ├── opencode.json   # committed agent definition — the seed carries its own identity
│   └── tools/query-memory.ts # Huck's read tool: search shared Mnemosyne memory
├── notebooks/          # tooling: ds.py, check.py, verify_loop.py + tests
├── chronicles/         # committed session chronicles (the durable record)
├── prompts/            # experiment/task prompts given to Huck
├── config/             # systemd: huck-check.service + huck-check.timer
├── state/              # runtime state (git-ignored)
└── plans/ACTIVE.md     # current position + next slice
```

## How to orient

`README.md` → `persona.md` → `EXPERIMENT.yml` → `plans/ACTIVE.md` → latest
chronicle in `chronicles/`.

## How to work

The fix→harden→generalise cycle. Chronicle via `ds.chronicle()`; query via
`ds.query()`; prove the loop with `python3 notebooks/verify_loop.py` (prints
`LOOP VERIFIED` on write→read→match). Drift scanner: `python3 notebooks/check.py`
(exit 0 clean, exit 1 drift). Resolution records live in shared Mnemosyne
memory so a fresh checkout knows what was already resolved.

## Current state

See `plans/ACTIVE.md`.
