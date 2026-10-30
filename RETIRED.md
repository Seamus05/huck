# RETIRED — 2026-10-29

Dave ordered the VM stopped and destroyed. This directory is the record.

## What happened

Huck ran **once**, on 2026-08-18 12:46, and never again. Three independent
breaks, any one of which was fatal:

1. **The timer never fired.** `huck-check.timer` was a *user* timer and
   `Linger=no` for user `huck`. A user timer only runs while that user has a
   session; the VM booted to a login prompt and nobody ever logged in. It
   reported `active` exactly while someone was ssh'd in — alive only while
   being observed.
2. **The model was gone.** Huck ran `qwen35-local/qwen3.5` — Qwen 3.5 9B on the
   A770 at `10.0.2.2:8898`. Nothing listens there now.
3. **The memory route could never work.** The wrapper set
   `OPENFRAME_MEMORY_URL=http://10.0.2.2:8381`, but the gateway binds
   `10.70.0.10:8381` — a LAN address. slirp's `10.0.2.2` maps to the host's
   *loopback*, so it cannot reach a LAN-bound service. That break was structural,
   not a stopped process.

And the "outer watchdog" named in `EXPERIMENT.yml` — "the host timer is the outer
watchdog" — was never built. The design was an agent that checks itself plus a
watchdog that checks the checker; neither was verified, so neither ever ran.

## What the experiment actually proved

Not the pattern. It proved the *failure mode of the pattern*: an isolated agent
needs three things that are easy to assume and hard to keep —

- a watchdog that is **not itself**, on a timer that runs without a login session;
- a model endpoint it can actually reach, at a route that survives the move into
  a VM;
- a memory route whose binding matches the network path (loopback vs LAN).

Also: the committed config said `opencode/deepseek-v4-flash-free` while the
machine ran `qwen35-local/qwen3.5`. The seed's committed identity described a
model Huck never used. Record and reality disagreed from the first day.

## Where the remains are

- This repo — 13 commits, branch `b1-memory-loop`, all pushed.
- `~/.openframe/state/archive/huck-vm-2026-10-29/` — the uncommitted diff,
  `state/`, the session database (18 messages), the agent persona, the launcher,
  the console log, and the cloud-init.
- `~/.openframe/config/component-registry.yaml` — entry `huck-vm`.

## Closed — the credential

`~/.secrets/huck-github-pat` and `~/.openframe/tokens/huck-github-pat` existed
after the VM was destroyed, because **destroying a machine does not revoke a
token**. Dave deleted the token in GitHub on 2026-10-29; the probe returned
`401 Bad credentials` and both files were removed.

Worth recording what the token could reach, because it was not "the huck repo":
fine-grained, with admin on five repositories (`Local-Yokel/llama.cpp-ly`,
`Seamus05/Lab`, `Seamus05/huck`, `Seamus05/bitmajor-trilogy`,
`Seamus05/openframe-molab`), expiring 2026-11-22 on its own. The blast radius of
a credential outlives the thing it was made for.
