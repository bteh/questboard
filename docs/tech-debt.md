# Technical debt and cleanup register

_Updated: July 16, 2026_

## Must resolve before a public local-agent release

### Personalized AI cache existed in Git history

Sixty generated `src/data/cache/ai_scores/*.json` files were tracked on `main`. Some contain personalized resume reasoning. The local-agent branch removes them from the index and ignores the directory while preserving the user's local files.

This does not remove older blobs from existing Git history. If the repository was public or shared, clean the remote history with a reviewed `git filter-repo` procedure and invalidate old clones. Do not force-push that rewrite without an explicit maintainer decision.

### Two local data roots

Source development currently uses `data/job_tracker.db`. The packaged Tauri app uses the platform application-data directory. The MCP installer detects the packaged app first and otherwise uses the source checkout, but Settings should eventually display the exact active data root and connection status.

### Local refresh concurrency

The desktop API and stdio MCP process can both open the same SQLite database safely through WAL, but their in-memory run guards are process-local. V1 documentation should tell users not to start simultaneous refreshes. The durable fix is a single local daemon that owns refresh leases while both UI and MCP act as clients.

### Legacy in-app AI remains

BYO API and Ollama paths still exist. They are compatibility paths, not the new primary product. Remove or isolate them only after the MCP workflow covers resume analysis, matching, and application drafting without regressions.

### Fit language is inconsistent

Legacy records contain `overall_score`, `recommendation`, and AI-generated reasoning. MCP candidate search deliberately omits those as proof and labels deterministic rank signals as retrieval only. The UI must adopt the same distinction before the next release.

## Intentionally parked

- hosted OAuth and multi-tenant MCP;
- hosted resume ranking;
- Questboard-funded model inference;
- auto-apply or outbound messaging;
- a public shared opportunity relay.

The preserved hosted experiment may inform later source infrastructure, but it should not be merged wholesale into the local-agent branch.
