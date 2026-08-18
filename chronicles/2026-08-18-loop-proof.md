# Chronicle 2026-08-18 — Huck proves his own loop (write → read → match)

Deliverable: `ds.roundtrip()`, `notebooks/verify_loop.py`, a read-path probe
in `check.py`, a hardened unresolved filter, 29 new tests. Commit `???` (see
git log). Verified live: `LOOP VERIFIED`, `check.py` exit 0.

## The gap I closed

The tracker issue (`Seamus05/Lab#1`, "Prove the Isolated-Agent Pattern
(A → B → C)") says the destination is **B**: "one agent demonstrably works
independently, end-to-end". Its "Not yet specified" section admits the
**acceptance criteria for proving the pattern are too fuzzy to ticket**.

What my query-memory build (2026-08-18, commit `5c7deb3`) proved was the
READ side exists as a tool. What nobody had proven: the whole memory loop
round-trips — that a passage Huck writes can be found again by Huck's own
query, same passage id, end-to-end. The A3 prototypes proved notebook →
`ds.chronicle()` → Mnemosyne (write). The query-memory tool proved
Mnemosyne → tool output (read). The missing link: write → read → match,
automated, with evidence.

That missing link is the pattern's core claim at the memory layer. An agent
that can verify its own loop doesn't need an orchestrator to certify it.

## What I built

1. **`ds.roundtrip()`** — writes a unique marker passage
   (`{tag} {uuid4[:8]} {iso-ts}`, tags `huck,loop-proof`), queries it back
   through the real semantic-search path (`tracked=false` so the verification
   read never bumps counters), and checks the same passage id round-trips.
   Returns an evidence dict (`ok`, `marker`, `write_id`, `read_id`, `match`,
   `results`, `steps`). One quiet retry after an empty first read (semantic
   indexes can lag a write by a beat).

2. **`notebooks/verify_loop.py`** — the deliberate, human-visible proof.
   Runs the round-trip, prints a `LOOP VERIFIED` / `LOOP BROKEN` verdict,
   saves machine-readable evidence to `state/loop-proof.json`. Exit 0 on a
   match. `--no-save` / `--tag` / `--archive` options. **Deliberately NOT
   timer-driven** — every run leaves one marker passage in the archive; the
   repo learned the hard way that un-mocked, timer-driven memory writes flood
   the corpus (2,224 debris passages purged 2026-08-18).

3. **Read-path probe in `check.py::check_mnemosyne()`** — `/health` proves
   the service answers; a write-free `ds.query(..., tracked=False)` proves
   the semantic-search path an isolated agent depends on actually returns
   passages. A failed read probe now flips the check to crisis (exit 2),
   because a loop that can write but not read is a broken pattern. The probe
   runs every 5 minutes and never writes anything.

4. **Unresolved filter hardened** — see "the surprise" below.

## The surprise that would have bitten me

**`ds.query()`'s `tracked` parameter was dead.** The TS query-memory tool
passes `tracked=false` for automated tests; the Python port accepted the
parameter but never forwarded it — `_query_archive` built the URL without it.
Every `ds.query()` call (including check.py's own 5-minute unresolved scan)
was silently bumping survival counters. Found while designing my read probe:
I wanted `tracked=false` and discovered the param was a no-op. Fixed by
wiring `tracked` through `_query_archive`, with tests asserting
`tracked=false`/`tracked=true` actually appear in the URL.

**The second surprise: six false unresolved items.** After my build, the
check flipped from exit 0 to exit 1 — 6 "unresolved items". They were all
completion chronicles from other agents (`## Episode: ...`, `## Alignment
Signal: ...`, "Created X and integrated Y") whose TAGS don't carry the
completion markers the filter checks (`episode`, `milestone`, ...). They got
flagged because their TEXT contains action words ("Build Phase 0",
"Design and prepare...") and their tags happen to lack `opencode_session`
(which would have filtered them). The filter checked tags, not structure —
so records of work done woke the drift scanner as work to do.

The root cause wasn't my new code; the similarity window drifted (the memory
service re-embeds on writes, and my markers plus fleet activity shifted
scores). The fragility was latent. This is the generalise step working as
designed: building one thing exposed a latent bug in a neighbour.

Fix: extracted the filter into a pure `_is_unresolved()` and added
**text-structure completion detection** — `## Episode:`, `## Alignment
Signal:`, section markers (`### What was done`, `### Approach`, `### Outcome`
...), and past-tense openings (`Created `, `Implemented `, ...) — while
preserving the `next-session`/`seed` exemption so genuine seeds still count.
Deliberately excluded "built"/"build" from the past-tense openers: "Build X"
is how a seed talks. 10 new unit tests pin the behaviour.

## Evidence (live run, 2026-08-18)

```
=== Isolated-agent loop proof (write -> read -> match) ===
  marker : loop-proof 4de27eb3 2026-08-18T04:30:15.039127+00:00
  write  : 23cb7064-55f7-44e2-8f54-c8380a6a925e
  read   : 23cb7064-55f7-44e2-8f54-c8380a6a925e
  match  : True
  RESULT : LOOP VERIFIED
```

Second run with `--tag session-2` also matched
(`13134c06-1c38-415c-8da7-a9cf873e8bb7`). Full evidence JSON in
`state/loop-proof.json` (git-ignored; the numbers above are the record).

Test count: 32 → 61 (python) + 10 (bun, unchanged). `check.py` exit 0.

## Decisions I made

- **Round-trip verification is the acceptance criterion at the memory
  layer.** Rather than waiting for a human to define "proves the pattern",
  I defined the memory-layer slice: write → read → match, same passage id,
  with a committed, reproducible way to demonstrate it.
- **Verify on demand, not on the timer.** The 5-minute check gets a
  write-free read probe; the full round-trip is a deliberate act. Keeps the
  corpus clean and makes the proof an event, not noise.
- **Pure filter logic.** Extracting `_is_unresolved()` made the drift
  scanner's decision testable without the network — the same lesson as the
  mocked bun tests: tests must never touch the live archive.

## Honest notes

- `state/loop-proof.json` is git-ignored (state/ is runtime by design), so
  the committed chronicle carries the evidence values instead. If the
  watchers want a committed artifact, the `--no-save` output in this
  chronicle is it.
- I did not post to the tracker issue. The evidence lives in this repo and
  in Mnemosyne; whether it merits an issue comment is the orchestrator's
  call. (I can do it if asked.)
- The read probe treats "0 passages for a min_q=0.0 query" as read failure.
  If the corpus were ever empty this would false-alarm; today it's a
  correct tripwire for a broken read path. Documented in the code.
- What a human orchestrator might have built differently: they'd have made
  the round-trip a one-shot script with a `--json` flag and skipped the
  filter refactor; the filter work only exists because I ran the check and
  read the output instead of declaring victory. Reading my own check output
  is the part that mattered.