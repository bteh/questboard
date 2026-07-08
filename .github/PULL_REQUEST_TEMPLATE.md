## Summary
<!-- 1-3 bullets on what this PR does and why -->

## Changes
<!-- Brief list of files / behavior changed -->

## Test plan
<!-- How you verified this works -->
- [ ] `pytest tests/ -q` green
- [ ] `cd frontend && pnpm run typecheck` clean
- [ ] `cd frontend && pnpm run lint` no new errors
- [ ] `cd frontend && pnpm run test` green (if frontend changed)
- [ ] Manually exercised the affected flow in `make dev` (if UI changed)

## Notes for reviewer
<!-- Anything weird, deferred, or worth a second pair of eyes -->
