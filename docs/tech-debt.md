# Technical debt and cleanup register

_Updated: July 16, 2026_

## Must resolve before a public local-agent release

### Personal data in Git history (blocker for a public repo)

Two kinds of personal data live in history and must be purged in ONE rewrite
before the repo goes public:

1. ~61 generated `src/data/cache/ai_scores/*.json` files (personalized resume
   reasoning tied to a named person). Removed from the index on this branch, but
   still present in older blobs.
2. The owner's actual resume PDFs — `backend/knowledge/*.pdf` / `knowledge/*.pdf`
   — added in `1a268d3`, removed from tracking in `c1b6616`, still in history.
   The branch's cache cleanup did NOT cover these.

Removing files from the index does not remove them from history. Keep the
GitHub repo **private** until the rewrite runs. Reviewed procedure (run on a
fresh clone, requires `git filter-repo`):

```bash
# 0) confirm what's still in history
git log --all --oneline -- 'src/data/cache/**' 'backend/knowledge/*.pdf' 'knowledge/*.pdf'

# 1) rewrite ALL history to drop caches + resume PDFs in one pass
git filter-repo --force \
  --path src/data/cache \
  --path-glob 'backend/knowledge/*.pdf' \
  --path-glob 'knowledge/*.pdf' \
  --invert-paths

# 2) re-add the remote (filter-repo drops it) and force-push every ref
git remote add origin git@github.com:bteh/questboard.git
git push --force --all origin
git push --force --tags origin

# 3) verify the blobs are gone (expect empty output)
git log --all --oneline -- 'src/data/cache/**' 'backend/knowledge/*.pdf' 'knowledge/*.pdf'
```

This is destructive and rewrites every commit hash: it needs an explicit
maintainer decision, and all existing clones/forks must be re-cloned (old copies
still carry the blobs). Do not run it as part of normal CI.

### Two local data roots

Source development currently uses `backend/data/job_tracker.db`; the Makefile and source MCP installer now point to that same file explicitly. The packaged Tauri app uses the platform application-data directory. Settings should eventually display the exact active data root and connection status, and a reviewed migration should consolidate legacy source databases without silently overwriting user data.

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
