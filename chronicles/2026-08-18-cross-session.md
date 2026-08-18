# Chronicle 2026-08-18 — Cross-session continuity from a fresh isolated worktree

Deliverable: resolution ledger lives in shared memory; `built ` completion
opener; `ds.passage_metadata()` normalizer; committed agent definition +
`check_agent_config()`; loop proof re-verified from the worktree. Branch
`b1-memory-loop`. 78 python tests pass, check.py exit 0.

## The situation I woke into

I was told I now live in a fresh git worktree of Seamus05/huck, on branch
`b1-memory-loop`, inside a Fresh editor workspace — my own
machine-equivalent, the closest yet to destination B ("one agent
demonstrably working end-to-end, independent"). The memory-layer loop proof
was done; three acceptance criteria remained: independent task execution,
self-direction, cross-session continuity.

Grounding from the worktree (the important verb: FROM the worktree, not the
old checkout):

- `python3 notebooks/check.py` → **exit 1, drift** — 2 "unresolved items"
  in memory (`0f2d383c` the growth seed, `bb9c7df0` the learn-bridge
  build chronicle).
- `python3 notebooks/verify_loop.py` → **LOOP VERIFIED** — the loop proof
  holds from this checkout; evidence saved to the worktree's own
  `state/loop-proof.json`.
- The catch: **both flagged passages were already in the main checkout's
  `state/resolved.json`** (2026-08-16). The worktree had no `state/` dir at
  all — `state/` is gitignored, so a fresh checkout forgets what was
  resolved. The drift scanner wasn't wrong, it was ignorant.

That was the live, falsifiable failure of the **cross-session continuity**
criterion, handed to me by my own grounding run.

## What I built

1. **Resolution ledger in shared memory.** `mark_resolved()` now chronicles
   a resolution record to Mnemosyne (metadata `source_file=huck/state/resolved.json`,
   `resolved_id=<passage id>`); `_resolved_ids_memory()` reads those records
   back via the deterministic `exists()` lookup; `resolved_ids()` merges
   local + memory. A fresh checkout with no `state/` dir reaches the same
   "what's done" conclusion as the checkout that did the work — the same
   Mnemosyne layer the loop proof verifies carries the knowledge across
   checkout boundaries. Falsifiable pass condition: seed a resolution in one
   checkout, wipe local state, fresh checkout still knows.

2. **`built ` is a completion opener.** The `bb9c7df0` passage starts
   "Built the learn() cross-agent bridge..." — a record of work done, but
   the drift filter flagged it because `COMPLETION_OPENERS` deliberately
   excluded "built"/"build" (chronicle: "'Build X' is how a seed talks").
   That conflation was wrong: "build " (imperative) is a seed, "built "
   (past tense) is a record, and the trailing 't' distinguishes them. Added
   `"built "` to the openers with tests on both sides (built → completion,
   build → still unresolved).

3. **`ds.passage_metadata()` — the surprise that bit twice.** The probe
   right after the build showed `_resolved_ids_memory()` returning `[]`
   even though `mark_resolved` reported success. Root cause: the Mnemosyne
   service returns metadata as **`metadata_`, a JSON-encoded string**, not
   `metadata` as a dict — so `(p.get("metadata") or {}).get(...)` is always
   empty on real passages. Worse: `check.py`'s `_is_unresolved` used the
   same dead read for its `source_file` filter, so that filter had silently
   stopped matching real passages too. One normalizer (`passage_metadata()`)
   reads both shapes; used in the resolution read path and the check filter.
   Tests pin both shapes (dict and `metadata_` string).

4. **The agent definition travels with the repo.** `.opencode/opencode.json`
   was gitignored — the worktree had no agent config, only the tools dir. I
   argued it both ways and concluded the config must travel: the pattern's
   claim is that a fresh checkout IS the seed, and a seed that can't
   instantiate its own agent depends on ambient host config — which is the
   dependency isolation is supposed to remove. Committed a minimal huck-only
   config (no provider secrets — those stay in global config), un-ignored it,
   and added `check_agent_config()` so the repo's own check fails if the
   agent definition ever goes missing. The check output now proves the seed
   is self-describing, exit 0 says it.

5. **README tree + prose synced** so the tree check stays clean, and the
   cross-session layer is documented for the next Huck.

## Evidence (live, from the worktree)

```
--- before (fresh worktree, no state/) ---
─ unresolved ─ 2 items   (0f2d383c seed, bb9c7df0 built record)
exit: 1

--- after ---
─ tests ─ PASS (78)
─ mnemosyne ─ reachable
─ readme tree ─ clean
─ agent config ─ ok — .opencode/opencode.json defines agent.huck
─ unresolved ─ 0 items
exit: 0

memory-only resolved ids: ['bb9c7df0', '0f2d383c']
```

Test count: 61 → 78 python (all mocked — no live memory in tests). Bun
tests: 10 pass in the main checkout; **fail in the fresh worktree** because
`.opencode/node_modules` is gitignored and didn't travel (noted, not fixed).

## Decisions and why

- **Cross-session continuity is the criterion to attack next** because my
  own grounding produced the failure — evidence, not prose. Fixing it also
  unblocks independent task execution (a fresh checkout can trust its memory
  of what's done) and self-direction (the drift scanner stops hallucinating
  work that's finished).
- **Resolution knowledge belongs in shared memory, not just a local file.**
  The loop proof proved Mnemosyne is the durable substrate; using it for
  state (not just observations) is the same pattern at a higher layer. The
  local file remains the offline cache, not the source of truth.
- **Memory writes are best-effort; the local file is the fallback.** A
  resolution that can't reach Mnemosyne still lands locally. The merge means
  either copy alone is enough.
- **`built ` over `build `**: don't fix the false positive by weakening the
  seed detector. The word shapes are different; the filter should use that.
- **Committed agent config is minimal, huck-only.** Providers and secrets
  stay in global config — the seed carries identity, not credentials.

## Honest notes

- The `metadata_` bug means the loop proof's earlier evidence (comment
  5323721033) rested on write→read paths that never exercised metadata
  filters. The read path that DOES use metadata (`exists()`, resolution
  lookup) was dead until now. If the loop proof ever claimed metadata
  survives a round-trip, it didn't verify that — this build does.
- `probe-1` resolution record remains in memory from my debug probe
  (harmless; it's in the resolved ledger, which only makes the scanner skip
  a passage that doesn't exist).
- I did NOT wire the worktree's own systemd timer — the timer's wrapper
  hardcodes the old `/home/theyokel/huck` path, and this Fresh workspace is
  orchestrator-driven anyway. The check still runs on demand; the 5-minute
  timer remains a main-checkout concern.
- Push: not done — asked implicitly by the brief ("ask if you're unsure").
  The branch is local; committing is the deliverable. Push is cheap once a
  reviewer wants it.
