# Exploration: ruflo for parallel sub-agent execution of GSD phases

**Date:** 2026-06-05
**Author:** Claude (autonomous session, for Pietro's review)
**Goal (Pietro):** Use `ruflo` to run GSD phase plans in **real parallel** — working around the worktree-spawning failure hit during Phase 1.
**Status:** Investigated (docs-first, no ruflo executed). Recommendation below. **Needs Pietro's decision before any implementation.**

---

## TL;DR / Recommendation

1. **ruflo's free mode does not solve the real bottleneck.** The bottleneck was never "spawning agents" — it was **isolated filesystem/git access per agent**. ruflo-as-MCP coordinates but still routes execution through Claude Code's own Task tool, which has the *same* worktree limitation that failed.
2. **ruflo's mode that *might* isolate (standalone `agentic-flow` swarm) needs a paid AI-provider API key** → violates project constraint #1 (zero-cost, Max-plan-only).
3. **The actual fix is free and already proven to work: manual `git worktree add`** via Bash. The harness's `isolation="worktree"` *feature* is what failed here ("not a git repository"); plain git worktrees work fine (validated 2026-06-05 — see Evidence).
4. **Recommendation:** Do **not** adopt ruflo for parallel execution under the zero-cost constraint. Instead, add a small **manual-worktree parallel-execution** path to how we run GSD waves. Keep ruflo optional/parked (its memory/coordination features are free in MCP mode but are a different value proposition).

---

## How ruflo executes agents (the cost question)

`ruflo` is the `ruvnet/claude-flow` framework (V3), shipped as the `ruflo` npm package. It has **two execution modes**, with very different cost profiles:

| Mode | How invoked | Who runs the work | Cost |
|------|-------------|-------------------|------|
| **MCP coordination** | `.mcp.json` → `npx -y ruflo mcp start` (his current setup, `autoStart: false`) | **Claude Code** (me) via the Task tool, using **Pietro's Max plan** | **Free** ✅ |
| **Standalone swarm** | `npx ruflo swarm init` / `hive-mind spawn` / `daemon` | `agentic-flow` router + `providers` (Anthropic/OpenRouter/… API keys) | **Paid API** ❌ |

Evidence from `.claude-flow/CAPABILITIES.md`: the `providers` command ("AI provider config", 5 subcommands) and the bundled `agentic-flow 3.0.0-alpha.1` ("Core coordination + ReasoningBank + Router") are the standalone execution engine; the MCP setup (`claude mcp add ruflo -- npx -y ruflo@latest`) is coordination-only and maps Claude Code's own agent scopes.

> Confidence: high on the architecture (well-documented claude-flow model). **Not runtime-verified** — I did not execute ruflo (respecting the rejected command + Pietro being away). The one thing worth a 1-line check when he's back: confirm the MCP swarm tools don't silently require a provider key.

## Why the free mode doesn't reach the goal

Pietro's goal is parallel **execution that writes files** (running plan 01-02 and 01-03 at the same time). Two plans editing the repo in parallel collide on the git index and working tree unless each agent has its **own working copy**. In MCP mode, ruflo would still hand the actual file-writing to Claude Code's Task sub-agents — the same ones whose `isolation="worktree"` failed here. So ruflo adds swarm topology + memory metadata, but the file-isolation problem is unchanged.

## The real fix (free, validated): manual git worktrees

The harness's *automatic* worktree feature errored with "not in a git repository" — a harness-level limitation, not a git problem. **Plain `git worktree add` via Bash works.**

### Evidence (validated 2026-06-05, then cleaned up)
```
git worktree add -b _wt_probe /tmp/jarvis-wt-test HEAD   → worktree with all 33 files
(in worktree) edit + git commit                          → isolated commit 9a7d4ed on _wt_probe
main HEAD                                                  → unchanged (68bcf1b)
git worktree remove --force + git branch -D               → clean
```

### Proposed approach (for Pietro's approval — NOT yet implemented)
For a GSD wave with N parallel plans on disjoint files:
1. Orchestrator captures `BASE=$(git rev-parse HEAD)`.
2. For each plan: `git worktree add -b gsd/<phase>-<plan> .worktrees/<plan> "$BASE"` (Bash, sequential to avoid the `.git/config.lock` race).
3. Spawn one `gsd-executor` agent per plan with an explicit instruction: *"Do ALL your work inside `/abs/path/.worktrees/<plan>` — cd there before every command; never touch the main tree."* (Sub-agents keep a persistent cwd within their own Bash.)
4. Agents run **truly in parallel**, each committing in its own worktree.
5. Orchestrator merges each worktree branch back into the feature branch, removes the worktrees, deletes the temp branches (mirrors GSD's existing worktree-cleanup step, just driven by Bash instead of the harness feature).

This is exactly what GSD's worktree mode intends — we just drive it with plain git because the harness shortcut is unavailable here. Zero cost, zero new dependencies.

### Risks / notes
- `.worktrees/` must be gitignored.
- Sequential `git worktree add` (round-trip spacing) avoids `.git/config.lock` contention.
- Disjoint-file check still required before parallelizing a wave (GSD already does this).
- Merge conflicts only if two plans touch the same file (GSD already forbids that within a wave).

## Where ruflo could still add value (optional, parked)
In **MCP mode (free)** ruflo's cross-agent **memory / knowledge graph / hooks** could enrich how agents share context — independent of parallel execution. If Pietro wants this, it's a separate, low-risk experiment: connect the MCP (`autoStart: true` or restart Claude Code), confirm no provider key is demanded, and try the `memory`/`hooks` tools. Not pursued autonomously (it needs the MCP live in-session and a runtime cost check).

## Decision needed from Pietro
- **(A)** Implement the manual-worktree parallel path for GSD waves (recommended; free; I can build + test it). 
- **(B)** Also wire ruflo's MCP for its free memory/coordination features (separate experiment).
- **(C)** Park parallel execution entirely (sequential within waves is correct and safe — it's what we used for Phase 1).
