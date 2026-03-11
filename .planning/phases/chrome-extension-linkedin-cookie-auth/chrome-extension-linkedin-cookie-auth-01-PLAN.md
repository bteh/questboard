---
phase: chrome-extension-linkedin-cookie-auth
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - backend/app/schemas/settings.py
  - backend/app/services/settings_service.py
  - backend/app/api/settings.py
  - src/job_finder/tools/scrapers/linkedin_auth.py
  - .env.example
autonomous: true

must_haves:
  truths:
    - "PUT /settings/linkedin accepts {li_at, jsessionid} and stores them encrypted on disk"
    - "GET /settings/linkedin returns connection status with TTL expiry info"
    - "DELETE /settings/linkedin removes stored cookie and returns disconnected status"
    - "POST /settings/linkedin/test validates stored cookie by making a real LinkedIn API call"
    - "Cookies older than 7 days are treated as expired and rejected"
    - "Scraper uses cookie-based auth via RequestsCookieJar instead of email/password"
    - "No references to LINKEDIN_EMAIL or LINKEDIN_PASSWORD remain in any modified file"
  artifacts:
    - path: "backend/app/schemas/settings.py"
      provides: "LinkedInCookieConfig, LinkedInStatus (updated), LinkedInDisconnectResponse Pydantic models"
      contains: "LinkedInCookieConfig"
    - path: "backend/app/services/settings_service.py"
      provides: "Fernet encryption, cookie file storage, TTL enforcement, disconnect, test connection"
      contains: "Fernet"
    - path: "backend/app/api/settings.py"
      provides: "Updated PUT (cookies), new DELETE, updated GET/POST endpoints"
      contains: "delete_linkedin"
    - path: "src/job_finder/tools/scrapers/linkedin_auth.py"
      provides: "Cookie-based _get_client() using RequestsCookieJar"
      contains: "RequestsCookieJar"
    - path: ".env.example"
      provides: "LINKEDIN_ENCRYPTION_KEY documentation, LINKEDIN_EMAIL/PASSWORD removed"
      contains: "LINKEDIN_ENCRYPTION_KEY"
  key_links:
    - from: "backend/app/api/settings.py"
      to: "backend/app/services/settings_service.py"
      via: "update_linkedin_cookies(), get_linkedin_status(), delete_linkedin_cookies(), test_linkedin_connection()"
      pattern: "settings_service\\.(update_linkedin_cookies|delete_linkedin_cookies)"
    - from: "backend/app/services/settings_service.py"
      to: "data/.linkedin_cookie"
      via: "Fernet-encrypted cookie file with TTL metadata"
      pattern: "Fernet|_COOKIE_FILE"
    - from: "src/job_finder/tools/scrapers/linkedin_auth.py"
      to: "backend/app/services/settings_service.py"
      via: "Reads decrypted cookies from storage to build RequestsCookieJar"
      pattern: "RequestsCookieJar|load_linkedin_cookies"
---

<objective>
Refactor the entire backend LinkedIn auth from email/password to cookie-based auth with Fernet encryption at rest. Update schemas, service layer, API routes, and the LinkedIn scraper to use cookie-based authentication.

Purpose: Establishes the foundational backend contract that the Chrome extension and frontend will POST cookies to. Cookies are encrypted via `cryptography.fernet` (AES-128-CBC + HMAC-SHA256) per user decision, stored in a file (not .env), and auto-expire after 7 days. The scraper is updated to create a `linkedin-api` client using `Linkedin('', '', cookies=cookiejar)` with `li_at` + `JSESSIONID` in a `RequestsCookieJar`.

Output: Working backend API for cookie-based LinkedIn auth with encrypted storage, TTL enforcement, disconnect capability, and a refactored scraper.
</objective>

<execution_context>
@/Users/briantehsayy/.claude/get-shit-done/workflows/execute-plan.md
@/Users/briantehsayy/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@backend/app/schemas/settings.py
@backend/app/services/settings_service.py
@backend/app/api/settings.py
@src/job_finder/tools/scrapers/linkedin_auth.py
@.env.example
</context>

<tasks>

<task type="auto">
  <name>Task 1: Backend schemas, Fernet encryption service, and API routes for cookie-based LinkedIn auth</name>
  <files>
    backend/app/schemas/settings.py
    backend/app/services/settings_service.py
    backend/app/api/settings.py
    .env.example
  </files>
  <action>
**schemas/settings.py:**
- Remove `LinkedInConfig(email, password)` class entirely.
- Add `LinkedInCookieConfig(BaseModel)` with fields: `li_at: str`, `jsessionid: str = ""` (jsessionid optional per planning context — can work without it).
- Update `LinkedInStatus(BaseModel)` to: `configured: bool = False`, `authenticated: bool = False`, `expires_at: str = ""` (ISO timestamp of when cookie expires), `message: str = ""`. Remove the `email` field.
- Add `LinkedInDisconnectResponse(BaseModel)` with fields: `success: bool`, `message: str`.

**services/settings_service.py:**
- Add imports: `import json`, `from datetime import datetime, timezone, timedelta`, `from pathlib import Path`. Lazy-import `from cryptography.fernet import Fernet` inside functions (heavy dep).
- Add constants: `_COOKIE_FILE = Path(_PROJECT_ROOT) / "data" / ".linkedin_cookie"`, `_COOKIE_TTL_DAYS = 7`.
- Add `_get_fernet() -> Fernet` function:
  - Reads `LINKEDIN_ENCRYPTION_KEY` from env.
  - If not set, generates a new key via `Fernet.generate_key()`, writes it to .env via `_write_env_vars({"LINKEDIN_ENCRYPTION_KEY": key.decode()})`, and also sets `os.environ`.
  - Returns `Fernet(key)`.
- Add `update_linkedin_cookies(li_at: str, jsessionid: str = "") -> dict`:
  - Validates `li_at` is non-empty (raise ValueError if empty).
  - Creates payload dict: `{"li_at": li_at, "jsessionid": jsessionid, "stored_at": datetime.now(timezone.utc).isoformat(), "expires_at": (datetime.now(timezone.utc) + timedelta(days=_COOKIE_TTL_DAYS)).isoformat()}`.
  - Encrypts `json.dumps(payload)` with `_get_fernet().encrypt()`.
  - Writes encrypted bytes to `_COOKIE_FILE` (create parent dir `data/` if needed).
  - Calls `_reset_linkedin_client()` (try/except ImportError).
  - Returns `get_linkedin_status()`.
- Add `load_linkedin_cookies() -> dict | None`:
  - If `_COOKIE_FILE` doesn't exist, return None.
  - Read encrypted bytes, decrypt with `_get_fernet().decrypt()`.
  - Parse JSON payload.
  - Check TTL: if `datetime.now(timezone.utc) > datetime.fromisoformat(payload["expires_at"])`, delete the file and return None (expired).
  - Return the payload dict `{"li_at": ..., "jsessionid": ..., "stored_at": ..., "expires_at": ...}`.
  - Wrap all in try/except — on any error (bad key, corrupted file), log warning, delete file, return None.
- Refactor `get_linkedin_status() -> dict`:
  - Remove all references to `LINKEDIN_EMAIL`/`LINKEDIN_PASSWORD`.
  - Call `load_linkedin_cookies()`. If None: return `{"configured": False, "authenticated": False, "expires_at": "", "message": "Not connected"}`.
  - If cookies exist: return `{"configured": True, "authenticated": False, "expires_at": payload["expires_at"], "message": "Connected (not tested)"}`. Note: `authenticated` stays False on GET — actual test is expensive.
- Refactor `test_linkedin_connection() -> dict`:
  - Remove email/password logic entirely.
  - Call `load_linkedin_cookies()`. If None: return status with `message: "No LinkedIn cookies stored"`.
  - Build a `http.cookiejar.MozillaCookieJar` or `requests.cookies.RequestsCookieJar` with `li_at` and `JSESSIONID` cookies for `.linkedin.com`.
  - Use `from linkedin_api import Linkedin` with `Linkedin('', '', cookies=jar)`.
  - Try `client.get_user_profile()` — if succeeds, return `authenticated: True, message: "Connected successfully"`.
  - On failure, return `authenticated: False, message: f"Connection failed: {e}"`.
- Add `delete_linkedin_cookies() -> dict`:
  - Delete `_COOKIE_FILE` if it exists.
  - Call `_reset_linkedin_client()` (try/except ImportError).
  - Remove `LINKEDIN_ENCRYPTION_KEY` from env if desired (optional — key can stay).
  - Return `{"success": True, "message": "LinkedIn disconnected"}`.
- Remove `update_linkedin_config(email, password)` function entirely.
- Remove `_mask_email()` function (no longer needed).
- Add helper `_reset_linkedin_client()` that imports and calls `_reset_client()` from the scraper (same try/except pattern as before).

**api/settings.py:**
- Update imports: replace `LinkedInConfig` with `LinkedInCookieConfig`, add `LinkedInDisconnectResponse`.
- Update `PUT /settings/linkedin`: Accept `LinkedInCookieConfig` instead of `LinkedInConfig`. Call `settings_service.update_linkedin_cookies(config.li_at, config.jsessionid)`.
- Update `GET /settings/linkedin`: No changes needed (calls `get_linkedin_status()`).
- Update `POST /settings/linkedin/test`: No changes needed (calls `test_linkedin_connection()`).
- Add `DELETE /settings/linkedin` endpoint with `response_model=LinkedInDisconnectResponse`. Calls `settings_service.delete_linkedin_cookies()`.

**.env.example:**
- Remove the `LINKEDIN_EMAIL` and `LINKEDIN_PASSWORD` lines and their comment block.
- Add new section:
  ```
  # -- LinkedIn Cookie Auth (optional) ------------------------------------
  # Encryption key for stored LinkedIn cookies. Auto-generated on first use
  # if not set. You can also generate one: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  # LINKEDIN_ENCRYPTION_KEY=
  ```

**Important:** Add `cryptography` to dependencies. In the task verification step, ensure `pip install cryptography` succeeds. Also update `pyproject.toml` to add `cryptography>=41.0.0` to the main dependencies list (not optional).
  </action>
  <verify>
1. `python -c "from cryptography.fernet import Fernet; print('OK')"` -- cryptography importable.
2. Start the backend: `cd backend && python -m uvicorn app.main:app --port 8000` (or however it starts).
3. `curl -X PUT http://localhost:8000/api/v1/settings/linkedin -H 'Content-Type: application/json' -d '{"li_at": "test_token_123"}'` -- returns 200 with LinkedInStatus JSON, `configured: true`.
4. `curl http://localhost:8000/api/v1/settings/linkedin` -- returns status showing configured.
5. `curl -X DELETE http://localhost:8000/api/v1/settings/linkedin` -- returns `{"success": true, "message": "LinkedIn disconnected"}`.
6. `curl http://localhost:8000/api/v1/settings/linkedin` -- returns `configured: false` after delete.
7. Verify `data/.linkedin_cookie` file is created on PUT and deleted on DELETE.
8. Verify `.env.example` has no LINKEDIN_EMAIL or LINKEDIN_PASSWORD references.
9. `grep -r "LINKEDIN_EMAIL\|LINKEDIN_PASSWORD" backend/ src/job_finder/tools/scrapers/linkedin_auth.py` -- no matches.
  </verify>
  <done>
- PUT /settings/linkedin accepts `{li_at, jsessionid}`, encrypts with Fernet, stores in `data/.linkedin_cookie`.
- GET /settings/linkedin returns status with TTL expiry.
- DELETE /settings/linkedin removes cookie file.
- POST /settings/linkedin/test validates cookie with a real LinkedIn API call.
- Cookies expire after 7 days (auto-deleted on load).
- No references to LINKEDIN_EMAIL/LINKEDIN_PASSWORD in modified files.
- `cryptography` added to project dependencies.
  </done>
</task>

<task type="auto">
  <name>Task 2: Refactor LinkedIn scraper to cookie-based auth</name>
  <files>
    src/job_finder/tools/scrapers/linkedin_auth.py
  </files>
  <action>
Refactor `linkedin_auth.py` to use cookie-based authentication instead of email/password:

1. **Remove all email/password references:**
   - Remove `os.getenv("LINKEDIN_EMAIL")` and `os.getenv("LINKEDIN_PASSWORD")` calls.
   - Remove the `is_configured()` function that checks for email/password env vars.

2. **Refactor `_get_client()` to use cookie-based auth:**
   ```python
   def _get_client():
       """Lazy singleton -- loads encrypted cookies from backend storage."""
       global _client
       if _client is not None:
           return _client

       try:
           # Import the backend service to load decrypted cookies
           import sys
           from pathlib import Path
           # Ensure backend is importable
           backend_dir = Path(__file__).resolve().parents[4] / "backend"
           if str(backend_dir) not in sys.path:
               sys.path.insert(0, str(backend_dir))

           from app.services.settings_service import load_linkedin_cookies
       except ImportError:
           # Fallback: try loading cookie file directly if backend not available
           logger.debug("Backend not importable, trying direct cookie load")
           load_linkedin_cookies = _load_cookies_direct

       cookies = load_linkedin_cookies()
       if not cookies:
           return None

       try:
           from linkedin_api import Linkedin
           from requests.cookies import RequestsCookieJar

           jar = RequestsCookieJar()
           jar.set("li_at", cookies["li_at"], domain=".linkedin.com", path="/")
           if cookies.get("jsessionid"):
               jar.set("JSESSIONID", cookies["jsessionid"], domain=".linkedin.com", path="/")

           _client = Linkedin('', '', cookies=jar)
           logger.info("LinkedIn authenticated via cookie")
           return _client
       except Exception as e:
           logger.warning("LinkedIn cookie auth failed (will fall back to guest mode): %s", e)
           return None
   ```

3. **Add `_load_cookies_direct()` as a fallback** for when the scraper runs standalone (e.g., via CLI without the FastAPI backend on sys.path):
   ```python
   def _load_cookies_direct() -> dict | None:
       """Load cookies directly from encrypted file (fallback when backend not importable)."""
       import json
       from pathlib import Path
       from datetime import datetime, timezone

       project_root = Path(__file__).resolve().parents[4]
       cookie_file = project_root / "data" / ".linkedin_cookie"
       if not cookie_file.exists():
           return None

       try:
           from cryptography.fernet import Fernet
           key = os.getenv("LINKEDIN_ENCRYPTION_KEY", "")
           if not key:
               # Try reading from .env file
               env_path = project_root / ".env"
               if env_path.exists():
                   for line in env_path.read_text().splitlines():
                       if line.startswith("LINKEDIN_ENCRYPTION_KEY="):
                           key = line.split("=", 1)[1].strip()
                           break
           if not key:
               return None

           fernet = Fernet(key.encode() if isinstance(key, str) else key)
           encrypted = cookie_file.read_bytes()
           decrypted = fernet.decrypt(encrypted)
           payload = json.loads(decrypted)

           # Check TTL
           expires_at = datetime.fromisoformat(payload["expires_at"])
           if datetime.now(timezone.utc) > expires_at:
               cookie_file.unlink(missing_ok=True)
               return None

           return payload
       except Exception as e:
           logger.warning("Failed to load LinkedIn cookies directly: %s", e)
           return None
   ```

4. **Add new `is_configured()` function** that checks for stored cookies instead of env vars:
   ```python
   def is_configured() -> bool:
       """Check if LinkedIn cookies are available."""
       client = _get_client()
       return client is not None
   ```
   Or simpler: check if the cookie file exists (faster, no decryption):
   ```python
   def is_configured() -> bool:
       """Check if LinkedIn cookie file exists."""
       from pathlib import Path
       project_root = Path(__file__).resolve().parents[4]
       return (project_root / "data" / ".linkedin_cookie").exists()
   ```

5. **Update module docstring** to reflect cookie-based auth instead of email/password.

6. **Keep `_reset_client()` as-is** -- it already just clears the singleton.

7. **Keep everything else unchanged** -- `search_linkedin_auth()`, `_get_job_safe()`, `_normalize_job()`, etc. are all still valid since they just use `client` which is now cookie-authenticated.
  </action>
  <verify>
1. `python -c "from job_finder.tools.scrapers.linkedin_auth import is_configured; print(is_configured())"` -- returns True if cookie file exists, False otherwise.
2. `grep -n "LINKEDIN_EMAIL\|LINKEDIN_PASSWORD" src/job_finder/tools/scrapers/linkedin_auth.py` -- no matches.
3. `grep -n "RequestsCookieJar\|cookies=jar\|load_linkedin_cookies" src/job_finder/tools/scrapers/linkedin_auth.py` -- confirms cookie-based approach.
4. `python -c "import ast; ast.parse(open('src/job_finder/tools/scrapers/linkedin_auth.py').read()); print('Syntax OK')"` -- valid Python.
  </verify>
  <done>
- `_get_client()` creates LinkedIn client via `Linkedin('', '', cookies=jar)` using `li_at` + `JSESSIONID` from encrypted storage.
- Falls back to direct cookie file loading when backend module not on sys.path (CLI usage).
- `is_configured()` checks for cookie file existence.
- No references to LINKEDIN_EMAIL or LINKEDIN_PASSWORD.
- All existing scraper logic (search, normalize, rate-limit) unchanged.
  </done>
</task>

</tasks>

<verification>
1. Backend starts without errors: `cd backend && python -m uvicorn app.main:app --port 8000`
2. Full PUT -> GET -> TEST -> DELETE cycle works via curl.
3. Encrypted cookie file created/deleted correctly in `data/` directory.
4. TTL enforcement: manually set `expires_at` to past date, confirm GET shows "Not connected".
5. Scraper file has valid syntax and no email/password references.
6. `grep -r "LINKEDIN_EMAIL\|LINKEDIN_PASSWORD" backend/ src/job_finder/tools/scrapers/linkedin_auth.py .env.example` -- zero matches.
</verification>

<success_criteria>
- All LinkedIn auth endpoints work with cookie-based payloads (PUT accepts li_at/jsessionid, DELETE disconnects).
- Cookies are encrypted at rest with Fernet in `data/.linkedin_cookie`.
- 7-day TTL enforced on cookie load.
- Scraper creates LinkedIn client from stored cookies via RequestsCookieJar.
- Zero references to LINKEDIN_EMAIL/LINKEDIN_PASSWORD in any modified file.
</success_criteria>

<output>
After completion, create `.planning/phases/chrome-extension-linkedin-cookie-auth/chrome-extension-linkedin-cookie-auth-01-SUMMARY.md`
</output>
