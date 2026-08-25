# Huck — ACTIVE

**Status:** Proving the isolated-agent pattern (A → B → C). Track B of
`Seamus05/Lab#1`.

## Latest chronicle

- `chronicles/2026-08-18-cross-session.md` — cross-session continuity build
  (resolution ledger in shared memory; fresh-checkout check.py matches the
  originating checkout). Branch `b1-memory-loop`. 78 python tests pass.
- `chronicles/2026-08-18-loop-proof.md` — the loop-proof build (write→read→match).
- `chronicles/2026-08-18-where-i-am.md` — position chronicle.

## Open slices / next steps

- Watchdog loop + query-tool round (see `prompts/`).
- Known worktree gap: `.opencode/node_modules` gitignored → bun tests for
  `query-memory.ts` can't run in a fresh worktree without reinstall.
  The python suite (78 tests) runs clean from a bare checkout.

## Pointers

- `EXPERIMENT.yml` — experiment definition.
- `persona.md` — identity + operating model.
- `notebooks/ds.py` — chronicle/query/learn/roundtrip helpers.
- Runtime: `state/dashboard.md`, `state/health.json` (both git-ignored).
