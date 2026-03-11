---
phase: chrome-extension-linkedin-cookie-auth
plan: 04
type: execute
wave: 3
depends_on:
  - "chrome-extension-linkedin-cookie-auth-01"
  - "chrome-extension-linkedin-cookie-auth-02"
  - "chrome-extension-linkedin-cookie-auth-03"
files_modified: []
autonomous: false

must_haves:
  truths:
    - "Complete end-to-end flow works: extension sends cookies -> backend encrypts and stores -> frontend shows connected -> scraper uses cookies"
    - "Manual paste flow works: user pastes li_at in settings -> backend stores -> test connection succeeds"
    - "Disconnect flow works: user clicks disconnect -> cookie file deleted -> status shows not connected"
    - "No email/password references remain anywhere in the codebase"
  artifacts: []
  key_links: []
---

<objective>
Verify the complete cookie-based LinkedIn auth flow end-to-end across all layers: Chrome extension, backend, frontend, and scraper.

Purpose: Ensure all four plans integrate correctly and the user can connect, test, and disconnect LinkedIn using cookie-based auth. Catch any integration issues between the independently-built components.

Output: Verified working system ready for use.
</objective>

<execution_context>
@/Users/briantehsayy/.claude/get-shit-done/workflows/execute-plan.md
@/Users/briantehsayy/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/chrome-extension-linkedin-cookie-auth/chrome-extension-linkedin-cookie-auth-01-SUMMARY.md
@.planning/phases/chrome-extension-linkedin-cookie-auth/chrome-extension-linkedin-cookie-auth-02-SUMMARY.md
@.planning/phases/chrome-extension-linkedin-cookie-auth/chrome-extension-linkedin-cookie-auth-03-SUMMARY.md
</context>

<tasks>

<task type="auto">
  <name>Task 1: Integration smoke tests and cleanup</name>
  <files></files>
  <action>
Run a comprehensive integration check across all layers:

1. **Codebase-wide cleanup check:**
   ```bash
   grep -rn "LINKEDIN_EMAIL\|LINKEDIN_PASSWORD" --include="*.py" --include="*.ts" --include="*.tsx" --include="*.js" --include="*.json" --include="*.yaml" --include="*.yml" .
   ```
   This should return ZERO matches (excluding .env files themselves and git history). If any matches found, fix them.

2. **Backend verification:**
   - Start backend: `cd backend && python -m uvicorn app.main:app --port 8000`
   - Test PUT: `curl -s -X PUT http://localhost:8000/api/v1/settings/linkedin -H 'Content-Type: application/json' -d '{"li_at":"test_cookie_abc123"}' | python -m json.tool`
   - Verify response has `configured: true` and `expires_at` is ~7 days from now.
   - Test GET: `curl -s http://localhost:8000/api/v1/settings/linkedin | python -m json.tool`
   - Verify `data/.linkedin_cookie` file exists and is not plaintext (contains binary/encrypted data).
   - Test DELETE: `curl -s -X DELETE http://localhost:8000/api/v1/settings/linkedin | python -m json.tool`
   - Verify response has `success: true`.
   - Verify `data/.linkedin_cookie` file is deleted.
   - Test GET again: verify `configured: false`.

3. **Frontend build verification:**
   - `cd frontend && npx tsc --noEmit` -- zero errors.
   - `cd frontend && npm run build` -- succeeds.

4. **Chrome extension validation:**
   - Verify `chrome-extension/manifest.json` is valid JSON with `manifest_version: 3`.
   - Verify all files referenced in manifest exist.

5. **Scraper syntax check:**
   - `python -c "import ast; ast.parse(open('src/job_finder/tools/scrapers/linkedin_auth.py').read()); print('OK')"` -- valid syntax.
   - Verify `RequestsCookieJar` is used in the file.

6. **Fix any issues found** in the above checks. Common issues:
   - Missing `apiDelete` function in the API client -- add it.
   - Import errors from renamed types.
   - CORS issues with extension fetch (should be fine since backend CORS allows localhost origins).

If all checks pass with no issues, no file changes needed.
  </action>
  <verify>
All commands in the action section pass without errors.
  </verify>
  <done>
- Zero LINKEDIN_EMAIL/LINKEDIN_PASSWORD references in codebase (excluding .env files).
- Backend PUT/GET/DELETE cycle works.
- Frontend compiles and builds.
- Chrome extension manifest is valid.
- Scraper has valid syntax with cookie-based auth.
  </done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <what-built>
Complete cookie-based LinkedIn auth replacing email/password across all layers:
1. Backend: Fernet-encrypted cookie storage with 7-day TTL, PUT/GET/DELETE/TEST endpoints.
2. Chrome extension: Manifest V3, reads li_at + JSESSIONID, sends to backend.
3. Frontend: Settings page with extension + manual paste modes, disconnect button, TTL display.
4. Scraper: Cookie-based LinkedIn client via RequestsCookieJar.
  </what-built>
  <how-to-verify>
**Backend API (via curl or frontend):**
1. Start backend: `cd backend && python -m uvicorn app.main:app --reload`
2. Start frontend: `cd frontend && npm run dev`
3. Open http://localhost:5173/settings

**Manual Paste Flow (easiest to test):**
4. In the LinkedIn card, switch to "Manual Paste" tab.
5. If you have a real LinkedIn li_at cookie, paste it and click "Connect LinkedIn".
6. Verify the status changes to "Connected" with an expiry date shown.
7. Click "Test Connection" -- should show success if cookie is valid.
8. Click "Disconnect LinkedIn" -- status should revert to "Not connected".

**Chrome Extension Flow (if you want to test):**
9. Open chrome://extensions, enable Developer mode.
10. Click "Load unpacked" and select the `chrome-extension/` folder.
11. Log into LinkedIn in Chrome.
12. Click the Launchboard extension icon.
13. Verify it shows "LinkedIn session detected".
14. Click "Send Cookies to Launchboard".
15. Verify the settings page now shows "Connected".

**Visual check:**
16. Verify the settings page LinkedIn card looks clean (no email/password fields visible).
17. Verify the onboarding wizard LinkedIn step (trigger via: `localStorage.setItem('launchboard-force-onboarding', 'true')` then refresh) shows the cookie-based flow.

**Verify old auth is gone:**
18. Confirm there are no email or password input fields anywhere in the LinkedIn section.
  </how-to-verify>
  <resume-signal>Type "approved" or describe issues to fix.</resume-signal>
</task>

</tasks>

<verification>
Complete end-to-end flow verified by human:
- Manual paste flow works.
- Chrome extension flow works (if tested).
- Disconnect flow works.
- No email/password UI visible.
- Settings and onboarding pages render correctly.
</verification>

<success_criteria>
- Human confirms the complete cookie-based LinkedIn auth flow works end-to-end.
- No visual or functional regressions in the settings page.
- Extension is loadable and functional in Chrome.
</success_criteria>

<output>
After completion, create `.planning/phases/chrome-extension-linkedin-cookie-auth/chrome-extension-linkedin-cookie-auth-04-SUMMARY.md`
</output>
