/**
 * test_query_memory.ts — tests for .opencode/tools/query-memory.ts
 *
 * Run: bun test notebooks/test_query_memory.ts  (from repo root)
 *
 * IMPORTANT: these tests mock fetch so they never touch the live Mnemosyne
 * service. The repo learned this the hard way — huck-check runs tests every
 * 5 minutes, and un-mocked tests once flooded the shared archive with
 * thousands of q=0.01 passages (see test_ds.py docstring, Aug 2026 purge).
 *
 * Real-service smoke tests live in the README/chronicle, not here.
 */
import { test, expect, mock, beforeEach, afterEach } from "bun:test"
import toolDef from "../.opencode/tools/query-memory.ts"

const CTX = {
  sessionID: "test",
  messageID: "test",
  agent: "huck",
  directory: process.cwd(),
  worktree: process.cwd(),
  abort: new AbortController().signal,
  metadata: () => {},
  ask: async () => {},
}

// The tool calls global fetch. bun's mock() only wraps a function — it does
// NOT replace globalThis.fetch — so tests would silently hit the live memory
// service (bad: the repo has a history of test suites flooding the archive).
// Instead, patch globalThis.fetch for the duration of each test.
const realFetch = globalThis.fetch

beforeEach(() => {
  globalThis.fetch = mock(async () => {
    throw new Error("fetch not mocked in this test")
  }) as unknown as typeof fetch
})

afterEach(() => {
  globalThis.fetch = realFetch
})

function makePassage(overrides: Partial<any> = {}) {
  return {
    id: `pass-${Math.random().toString(36).slice(2, 8)}`,
    text: "A passage about shared memory and agent chronicles.",
    q_value: 0.5,
    tags: ["huck", "chronicle"],
    created_at: "2026-08-17T00:00:00+00:00",
    similarity: 0.7,
    ...overrides,
  }
}

function mockFetchOk(passages: any[]) {
  globalThis.fetch = mock(async (url: any, init?: any) => {
    const urlStr = String(url)
    const archive = new URL(urlStr).searchParams.get("archive_id")
    // Only answer for the archive the test asks about, so merge is exercised.
    if (archive && !["default", "agent-uuid"].includes(archive)) {
      return new Response(JSON.stringify({ passages: [] }), { status: 200 })
    }
    return new Response(JSON.stringify({ passages }), { status: 200 })
  }) as unknown as typeof fetch
  return globalThis.fetch
}

test("empty query returns error, no fetch", async () => {
  // @ts-ignore
  const r = await toolDef.execute({ query: "" }, CTX as any)
  expect(r).toContain("Error")
  // The beforeEach mock should never be called for an empty query.
  expect((globalThis.fetch as any).mock.calls.length).toBe(0)
})

test("whitespace query returns error", async () => {
  // @ts-ignore
  const r = await toolDef.execute({ query: "   \n " }, CTX as any)
  expect(r).toContain("Error")
  expect((globalThis.fetch as any).mock.calls.length).toBe(0)
})

test("limit is clamped to min 1", async () => {
  mockFetchOk([makePassage()])
  // @ts-ignore
  const r = await toolDef.execute({ query: "kairos", limit: -5, tracked: false }, CTX as any)
  expect(r).toContain("1 result")
  expect(r).not.toContain("5 results")
})

test("limit is clamped to max 50", async () => {
  const many = Array.from({ length: 60 }, () => makePassage())
  mockFetchOk(many)
  // @ts-ignore
  const r = await toolDef.execute({ query: "kairos", limit: 9999, tracked: false }, CTX as any)
  // 5 archives each return 50 → dedupe → should clamp to 50 shown
  expect(r).toContain("50 results")
})

test("min_q is clamped to 0..1", async () => {
  mockFetchOk([makePassage()])
  // @ts-ignore
  const r = await toolDef.execute({ query: "kairos", min_q: 7, tracked: false }, CTX as any)
  expect(r).toContain("min_q=1.00")
})

test("results are formatted with id, tags, text", async () => {
  mockFetchOk([makePassage({ id: "abc-123", text: "Hello shared memory world" })])
  // @ts-ignore
  const r = await toolDef.execute({ query: "hello", limit: 1, tracked: false }, CTX as any)
  expect(r).toContain("abc-123")
  expect(r).toContain("Hello shared memory world")
  expect(r).toContain("tags:")
})

test("cross-archive merge dedupes by id", async () => {
  const shared = makePassage({ id: "dup-1", text: "Same passage both archives" })
  mockFetchOk([shared, makePassage({ id: "dup-1", text: "Same passage both archives" })])
  // @ts-ignore
  const r = await toolDef.execute({ query: "dup", limit: 10, tracked: false }, CTX as any)
  const count = (r.match(/dup-1/g) || []).length
  // id printed once per result line; dedupe means it appears exactly once
  expect(count).toBe(1)
})

test("single-archive failure reports partial results, not crash", async () => {
  globalThis.fetch = mock(async (url: any) => {
    const urlStr = String(url)
    if (urlStr.includes("archive_id=default")) {
      return new Response(JSON.stringify({ passages: [makePassage()] }), { status: 200 })
    }
    throw new Error("Unable to connect. Is the computer able to access the url?")
  }) as unknown as typeof fetch
  // @ts-ignore
  const r = await toolDef.execute({ query: "kairos", limit: 1, tracked: false }, CTX as any)
  expect(r).toContain("1 result")
  expect(r).toContain("⚠")
  expect(r).toContain("failed")
})

test("all archives failing gives clear unreachable message", async () => {
  globalThis.fetch = mock(async () => {
    throw new Error("Unable to connect. Is the computer able to access the url?")
  }) as unknown as typeof fetch
  // @ts-ignore
  const r = await toolDef.execute({ query: "kairos", limit: 1, tracked: false }, CTX as any)
  expect(r).toContain("No passages found")
  expect(r).toContain("All archives failed")
  expect(r).toContain("memory service may be unreachable")
})

test("nonsense query returns clean empty result", async () => {
  mockFetchOk([])
  // @ts-ignore
  const r = await toolDef.execute({ query: "zzzqqqwww", limit: 1, tracked: false }, CTX as any)
  expect(r).toContain("0 results")
  expect(r).toContain("No passages found")
})