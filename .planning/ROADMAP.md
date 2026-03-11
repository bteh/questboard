# Launchboard Roadmap

## Phases

### Phase: Chrome Extension + Cookie-Based LinkedIn Auth

**Goal:** Replace email/password LinkedIn auth with cookie-based auth using a Chrome extension and Fernet encryption at rest. Provide extension (primary) and manual paste (fallback) auth modes.

**Status:** Planned
**Plans:** 4 plans

Plans:
- [ ] chrome-extension-linkedin-cookie-auth-01-PLAN.md -- Backend schemas, Fernet encryption service, API routes, and scraper refactor to cookie-based auth
- [ ] chrome-extension-linkedin-cookie-auth-02-PLAN.md -- Chrome Manifest V3 extension for auto-extracting LinkedIn session cookies
- [ ] chrome-extension-linkedin-cookie-auth-03-PLAN.md -- Frontend UI refactor: settings page, hooks, API client, onboarding wizard
- [ ] chrome-extension-linkedin-cookie-auth-04-PLAN.md -- Integration verification and human sign-off
