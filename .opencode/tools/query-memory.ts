/**
 * query-memory.ts — Search shared memory (Mnemosyne archival passages).
 *
 * Huck's read-side counterpart to send-message / write-observation.
 *
 * Discovery notes (2026-08-17):
 *  - The memory service (MEMORY_URL, default http://10.70.0.10:8381) filters
 *    semantic search on `archive_id`, NOT on the agent in the URL path — the
 *    path segment `/v1/agents/{agent_id}/archival-memory` is cosmetic.
 *  - The shared corpus is split across several archives:
 *      agent-b0c24e6b-...  (~757 passages) — written by the inline tools
 *                           (send-message/write-observation)
 *      default             (~389 passages) — written by ds.chronicle()
 *      infra-lessons, phaedrus, mori        — smaller archives
 *    So a query tool that only hits `archive_id=default` (like ds.query())
 *    sees only ~34% of the corpus. This tool searches ALL archives and
 *    merges/dedupes by default.
 *  - `tracked=true` bumps survival counters ("genuine demand"). Real agent
 *    queries should leave it on; automated tests pass tracked=false.
 */

import { tool } from "@opencode-ai/plugin"

const MEMORY_URL = process.env.MEMORY_SERVICE_URL || "http://10.70.0.10:8381"
const MNEMOSYNE_ID =
  process.env.MNEMOSYNE_ID || "agent-b0c24e6b-303d-433a-a166-4881c563661d"

// Archives that make up the shared corpus. The UUID archive is where the
// inline tools write; "default" is where ds.chronicle() writes.
const KNOWN_ARCHIVES = [
  MNEMOSYNE_ID,
  "default",
  "infra-lessons",
  "phaedrus",
  "mori",
]

interface Passage {
  id: string
  text: string
  q_value?: number
  tags?: string[]
  metadata_?: string
  created_at?: string
  similarity?: number
  archive_id?: string
}

function clamp(n: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, n))
}

async function searchArchive(
  queryText: string,
  archiveId: string,
  limit: number,
  minQ: number,
  orderBy: string,
  tracked: boolean,
): Promise<Passage[]> {
  const params = new URLSearchParams({
    query: queryText,
    limit: String(limit),
    min_q: String(minQ),
    archive_id: archiveId,
    order_by: orderBy,
    tracked: tracked ? "true" : "false",
  })
  const url = `${MEMORY_URL}/v1/agents/${MNEMOSYNE_ID}/archival-memory?${params}`
  const res = await fetch(url, {
    signal: AbortSignal.timeout(20000),
  })
  if (!res.ok) {
    const body = await res.text().catch(() => "?")
    throw new Error(`archive "${archiveId}" returned ${res.status}: ${body}`)
  }
  const data = (await res.json()) as { passages?: Passage[] }
  return (data.passages || []).map((p) => ({ ...p, archive_id: archiveId }))
}

function truncate(text: string, maxLen: number): string {
  if (!text) return ""
  const oneLine = text.replace(/\s+/g, " ").trim()
  if (oneLine.length <= maxLen) return oneLine
  return oneLine.substring(0, maxLen) + "…"
}

function formatDate(iso?: string): string {
  if (!iso) return "?"
  return iso.substring(0, 19).replace("T", " ")
}

export default tool({
  description:
    "Search shared memory (Mnemosyne archival passages) by semantic similarity. " +
    "Searches ALL known archives by default (the corpus is split across the UUID " +
    "archive, 'default', 'infra-lessons', 'phaedrus', 'mori') and merges + dedupes. " +
    "Use this to learn what other agents (Phaedrus, Carlin, Jung, Kairos, ...) " +
    "have chronicled. Pass archive='default' or an agent UUID to narrow to one archive.",
  args: {
    query: tool.schema.string({
      description: "Semantic search text — what you want to find in shared memory",
    }),
    limit: tool.schema.number({
      description: "Max results to return (default 5, clamped 1-50)",
      optional: true,
    }),
    min_q: tool.schema.number({
      description:
        "Minimum q_value (quality/importance) floor, 0.0-1.0. Default 0.0 for broad discovery",
      optional: true,
    }),
    archive: tool.schema.string({
      description:
        "Archive to search. 'all' (default) searches every known archive and merges. " +
        "Use a specific archive id (e.g. 'default' or the agent UUID) to narrow.",
      optional: true,
    }),
    order_by: tool.schema.enum(["similarity", "recency"], {
      description: "Sort results by semantic similarity (default) or recency",
      optional: true,
    }),
    tracked: tool.schema.boolean({
      description:
        "Bump survival counters (genuine demand tracking). Default true. " +
        "Set false for automated tests / bulk probing.",
      optional: true,
    }),
  },
  async execute(args) {
    const {
      query,
      limit = 5,
      min_q = 0.0,
      archive = "all",
      order_by = "similarity",
      tracked = true,
    } = args

    const q = (query || "").trim()
    if (!q) {
      return "Error: query is required and cannot be empty."
    }

    const k = clamp(Math.floor(limit), 1, 50)
    const minQ = clamp(min_q, 0, 1)

    // Per-archive fetch is 2x the requested limit so the cross-archive merge
    // has better recall, then we re-rank and truncate to `k` at the end.
    const perArchive = clamp(k * 2, 1, 50)

    const targets =
      archive === "all" ? KNOWN_ARCHIVES : archive.split(",").map((s) => s.trim()).filter(Boolean)

    if (targets.length === 0) {
      return "Error: archive list is empty."
    }

    // Query archives; if one archive fails, note it and continue — partial
    // results beat a total failure when one archive is down.
    const settled = await Promise.all(
      targets.map(async (archiveId) => {
        try {
          const passages = await searchArchive(q, archiveId, perArchive, minQ, order_by, tracked)
          return { archiveId, passages, error: null as string | null }
        } catch (e) {
          return {
            archiveId,
            passages: [] as Passage[],
            error: e instanceof Error ? e.message : String(e),
          }
        }
      }),
    )

    const errors = settled.filter((s) => s.error).map((s) => `${s.archiveId}: ${s.error}`)

    // Merge, dedupe by id, re-rank.
    const byId = new Map<string, Passage>()
    for (const s of settled) {
      for (const p of s.passages) {
        if (p.id && !byId.has(p.id)) byId.set(p.id, p)
      }
    }
    let merged = [...byId.values()]
    if (order_by === "recency") {
      merged.sort(
        (a, b) =>
          new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime(),
      )
    } else {
      merged.sort(
        (a, b) => (b.similarity ?? -1) - (a.similarity ?? -1),
      )
    }
    const results = merged.slice(0, k)

    const searched = settled.map((s) => s.archiveId)
    let out = `Query: "${q}" — ${results.length} result${results.length === 1 ? "" : "s"}`
    out += ` (archives: ${searched.join(", ")})`
    out += `\nmin_q=${minQ.toFixed(2)} order=${order_by} tracked=${tracked ? "true" : "false"}\n`

    if (results.length === 0) {
      out += "\nNo passages found. Try a different query, lower min_q, or raise limit."
    }

    results.forEach((p, i) => {
      const sim = p.similarity != null ? p.similarity.toFixed(3) : "?"
      const qv = p.q_value != null ? p.q_value.toFixed(3) : "?"
      const tags = (p.tags && p.tags.length ? p.tags.join(", ") : "-")
      out += `\n[${i + 1}] sim=${sim} q=${qv} | ${p.archive_id || "?"} | ${formatDate(p.created_at)}\n`
      out += `    tags: ${tags}\n`
      out += `    ${truncate(p.text || "(no text)", 400)}\n`
      out += `    id: ${p.id}\n`
    })

    if (errors.length > 0) {
      out += `\n⚠ ${errors.length} archive(s) failed (partial results):\n`
      for (const e of errors.slice(0, 5)) out += `  - ${e}\n`
      if (errors.length === targets.length) {
        out += `\nAll archives failed — the memory service may be unreachable at ${MEMORY_URL}.\n`
      }
    }

    return out
  },
})
