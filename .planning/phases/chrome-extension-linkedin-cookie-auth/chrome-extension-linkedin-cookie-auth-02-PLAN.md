---
phase: chrome-extension-linkedin-cookie-auth
plan: 02
type: execute
wave: 1
depends_on: []
files_modified:
  - chrome-extension/manifest.json
  - chrome-extension/popup.html
  - chrome-extension/popup.js
  - chrome-extension/popup.css
  - chrome-extension/background.js
  - chrome-extension/icons/icon16.svg
  - chrome-extension/icons/icon48.svg
  - chrome-extension/icons/icon128.svg
autonomous: true

must_haves:
  truths:
    - "Extension popup shows a 'Send Cookies to Launchboard' button when user is logged into LinkedIn"
    - "Clicking the button reads li_at and JSESSIONID cookies via chrome.cookies.get() and sends them to the backend"
    - "Extension popup shows success/error status after sending cookies"
    - "Backend URL is configurable in the popup (default: http://localhost:8000)"
    - "Extension uses Manifest V3 with minimal permissions (cookies for linkedin.com only)"
  artifacts:
    - path: "chrome-extension/manifest.json"
      provides: "Manifest V3 config with cookies permission for linkedin.com"
      contains: "manifest_version.*3"
    - path: "chrome-extension/popup.html"
      provides: "Extension popup UI structure"
      contains: "popup.js"
    - path: "chrome-extension/popup.js"
      provides: "Cookie reading via chrome.cookies.get() and fetch() to backend"
      contains: "chrome.cookies.get"
    - path: "chrome-extension/popup.css"
      provides: "Popup styling matching Launchboard design"
    - path: "chrome-extension/background.js"
      provides: "Service worker for Manifest V3"
  key_links:
    - from: "chrome-extension/popup.js"
      to: "chrome.cookies API"
      via: "chrome.cookies.get() for li_at and JSESSIONID on .linkedin.com"
      pattern: "chrome\\.cookies\\.get"
    - from: "chrome-extension/popup.js"
      to: "http://localhost:8000/api/v1/settings/linkedin"
      via: "fetch() PUT request with {li_at, jsessionid} payload"
      pattern: "fetch.*settings/linkedin"
---

<objective>
Create the Launchboard companion Chrome extension that auto-extracts LinkedIn session cookies and sends them to the backend.

Purpose: Provides a one-click way for non-technical users to authenticate LinkedIn. The extension reads `li_at` and `JSESSIONID` cookies from the browser (which are set when the user is logged into LinkedIn) and POSTs them to the running Launchboard backend. Uses Chrome Manifest V3 per user decision.

Output: Complete Chrome extension directory ready to load via chrome://extensions in developer mode, or eventually publish to Chrome Web Store.
</objective>

<execution_context>
@/Users/briantehsayy/.claude/get-shit-done/workflows/execute-plan.md
@/Users/briantehsayy/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@backend/app/schemas/settings.py
@backend/app/api/settings.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Chrome extension manifest, service worker, and icons</name>
  <files>
    chrome-extension/manifest.json
    chrome-extension/background.js
    chrome-extension/icons/icon16.svg
    chrome-extension/icons/icon48.svg
    chrome-extension/icons/icon128.svg
  </files>
  <action>
**manifest.json** -- Create a Manifest V3 extension:
```json
{
  "manifest_version": 3,
  "name": "Launchboard - LinkedIn Cookie Bridge",
  "version": "1.0.0",
  "description": "Securely sends your LinkedIn session cookies to Launchboard for authenticated job searching.",
  "permissions": ["cookies"],
  "host_permissions": ["https://*.linkedin.com/*"],
  "action": {
    "default_popup": "popup.html",
    "default_icon": {
      "16": "icons/icon16.svg",
      "48": "icons/icon48.svg",
      "128": "icons/icon128.svg"
    }
  },
  "background": {
    "service_worker": "background.js"
  },
  "icons": {
    "16": "icons/icon16.svg",
    "48": "icons/icon48.svg",
    "128": "icons/icon128.svg"
  }
}
```

Key decisions per user locked requirements:
- `manifest_version: 3` (required for Chrome Web Store).
- `permissions: ["cookies"]` -- needed for `chrome.cookies.get()`.
- `host_permissions` for `*.linkedin.com` -- limits cookie access to LinkedIn only.
- No `storage` permission needed (backend URL stored in popup localStorage, or we can use a simple input).

**background.js** -- Minimal service worker (required by Manifest V3 even if we do most work in popup):
```javascript
// Service worker for Launchboard LinkedIn Cookie Bridge
// Cookie reading happens in popup.js via chrome.cookies.get()
// This file is required by Manifest V3 but currently minimal.

chrome.runtime.onInstalled.addListener(() => {
  console.log('Launchboard LinkedIn Cookie Bridge installed');
});
```

**Icons** -- Create simple SVG placeholder icons at 3 sizes (16x16, 48x48, 128x128). Use a simple rocket/briefcase shape in the brand blue color (#4F46E5 or similar). Keep SVGs minimal -- just a colored circle with "LB" text or a simple shape. These are functional placeholders.

For icon16.svg: A 16x16 SVG with a small blue circle and white "L" letter.
For icon48.svg: A 48x48 SVG with the same design scaled up.
For icon128.svg: A 128x128 SVG with the same design, slightly more detailed.

Note: SVGs work in Manifest V3 for Chrome extensions. If there are issues, the executor should convert to PNG, but SVGs are preferred for simplicity.
  </action>
  <verify>
1. `cat chrome-extension/manifest.json | python -m json.tool` -- valid JSON.
2. Verify manifest has `manifest_version: 3`, `permissions: ["cookies"]`, `host_permissions` includes linkedin.com.
3. All icon files exist at the expected paths.
4. `background.js` exists and has valid JS syntax.
  </verify>
  <done>
- manifest.json is valid Manifest V3 with cookies permission scoped to linkedin.com.
- background.js service worker exists and is referenced in manifest.
- Three icon files (16, 48, 128) exist in icons/ directory.
  </done>
</task>

<task type="auto">
  <name>Task 2: Extension popup UI and cookie extraction logic</name>
  <files>
    chrome-extension/popup.html
    chrome-extension/popup.js
    chrome-extension/popup.css
  </files>
  <action>
**popup.html** -- Simple, clean popup layout:
- Header: "Launchboard" with small icon/branding.
- Status area: Shows whether LinkedIn cookies were detected in the browser.
- Main action button: "Send Cookies to Launchboard" (disabled if no cookies detected).
- Settings section (collapsible): Backend URL input field, default to `http://localhost:8000`.
- Result area: Shows success/error message after sending.
- Footer: Brief security note ("Cookies are encrypted and stored locally on your machine").
- Size: approximately 320px wide (standard popup width), content determines height.
- Link popup.css and popup.js.

**popup.css** -- Clean styling:
- Use a design language consistent with Launchboard (clean, minimal, blue accent #4F46E5).
- Body: `width: 320px`, `font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif`, `padding: 16px`.
- Button styles: primary button with blue background, disabled state grayed out, loading state with opacity.
- Status indicators: green dot for "cookies found", red dot for "not logged in", blue dot for "sending".
- Input field for backend URL: clean border, monospace font for the URL.
- Result messages: success in green, error in red, with appropriate background colors.

**popup.js** -- Core logic with these functions:

1. **`checkCookies()`** -- Called on popup load. Uses `chrome.cookies.get()` to check for `li_at` and `JSESSIONID`:
   ```javascript
   async function checkCookies() {
     const liAt = await chrome.cookies.get({ url: 'https://www.linkedin.com', name: 'li_at' });
     const jsessionid = await chrome.cookies.get({ url: 'https://www.linkedin.com', name: 'JSESSIONID' });

     if (liAt && liAt.value) {
       // Show "LinkedIn cookies detected" status (green)
       // Enable the send button
       updateStatus('found', 'LinkedIn session detected');
     } else {
       // Show "Not logged into LinkedIn" status (red)
       // Disable the send button
       // Show hint: "Please log into LinkedIn in this browser first"
       updateStatus('not-found', 'Not logged into LinkedIn');
     }

     return { liAt: liAt?.value || '', jsessionid: jsessionid?.value || '' };
   }
   ```

2. **`sendCookies()`** -- Called when user clicks the send button:
   ```javascript
   async function sendCookies() {
     const btn = document.getElementById('send-btn');
     const resultEl = document.getElementById('result');
     btn.disabled = true;
     btn.textContent = 'Sending...';
     resultEl.textContent = '';

     try {
       const { liAt, jsessionid } = await checkCookies();
       if (!liAt) {
         showResult('error', 'No LinkedIn cookies found. Please log into LinkedIn first.');
         return;
       }

       const backendUrl = document.getElementById('backend-url').value.replace(/\/$/, '');
       const response = await fetch(`${backendUrl}/api/v1/settings/linkedin`, {
         method: 'PUT',
         headers: { 'Content-Type': 'application/json' },
         body: JSON.stringify({ li_at: liAt, jsessionid: jsessionid }),
       });

       if (!response.ok) {
         const error = await response.text();
         throw new Error(`Server error: ${response.status} ${error}`);
       }

       const data = await response.json();
       showResult('success', 'Cookies sent successfully! LinkedIn is now connected in Launchboard.');

       // Optionally auto-trigger a test
       // await testConnection(backendUrl);
     } catch (e) {
       if (e.message.includes('Failed to fetch') || e.message.includes('NetworkError')) {
         showResult('error', 'Cannot reach Launchboard backend. Make sure it is running at the URL below.');
       } else {
         showResult('error', `Failed: ${e.message}`);
       }
     } finally {
       btn.disabled = false;
       btn.textContent = 'Send Cookies to Launchboard';
     }
   }
   ```

3. **Backend URL persistence** -- Store the backend URL in localStorage so it persists across popup opens:
   ```javascript
   const DEFAULT_URL = 'http://localhost:8000';

   function loadBackendUrl() {
     const saved = localStorage.getItem('launchboard-backend-url');
     document.getElementById('backend-url').value = saved || DEFAULT_URL;
   }

   function saveBackendUrl() {
     const url = document.getElementById('backend-url').value;
     localStorage.setItem('launchboard-backend-url', url);
   }
   ```

4. **Helper functions:**
   - `updateStatus(state, message)` -- Updates the status indicator (green/red/blue dot + text).
   - `showResult(type, message)` -- Shows success/error message in the result area.

5. **DOMContentLoaded listener:**
   ```javascript
   document.addEventListener('DOMContentLoaded', () => {
     loadBackendUrl();
     checkCookies();
     document.getElementById('send-btn').addEventListener('click', sendCookies);
     document.getElementById('backend-url').addEventListener('change', saveBackendUrl);
   });
   ```

**Important implementation notes:**
- The JSESSIONID cookie value from LinkedIn often starts with `"ajax:..."` (with quotes). Pass the raw value as-is -- the backend and linkedin-api handle it.
- Use async/await throughout (not callbacks) for cleaner code.
- No external dependencies -- vanilla JS only.
- The popup must handle the case where the backend is not running (fetch fails) gracefully.
  </action>
  <verify>
1. Open `chrome-extension/popup.html` in a browser directly -- layout renders correctly (won't have chrome.cookies API but structure visible).
2. `node -c "$(cat chrome-extension/popup.js)"` -- valid JavaScript syntax (Node won't have chrome.* APIs but syntax check works).
3. All three files exist and reference each other correctly (popup.html links popup.css and popup.js).
4. `grep "chrome.cookies.get" chrome-extension/popup.js` -- confirms cookie reading.
5. `grep "fetch.*settings/linkedin" chrome-extension/popup.js` -- confirms API call to backend.
6. `grep "localhost:8000" chrome-extension/popup.js` -- confirms default backend URL.
  </verify>
  <done>
- popup.html renders a clean extension popup with status, send button, backend URL config, and result area.
- popup.js reads li_at and JSESSIONID via chrome.cookies.get() and sends them to backend via fetch() PUT.
- Backend URL is configurable and persisted in localStorage (default: http://localhost:8000).
- Error handling covers: no cookies found, backend unreachable, server errors.
- popup.css provides clean styling consistent with Launchboard design.
  </done>
</task>

</tasks>

<verification>
1. Extension directory has all required files: manifest.json, popup.html, popup.js, popup.css, background.js, icons/*.
2. `cat chrome-extension/manifest.json | python -m json.tool` -- valid JSON with correct manifest_version, permissions, popup reference.
3. Popup JS has valid syntax and uses chrome.cookies.get() API.
4. Popup HTML is self-contained (no external CDN dependencies).
5. All files are vanilla web tech -- no build step required.
</verification>

<success_criteria>
- Complete Chrome extension in `chrome-extension/` directory loadable via chrome://extensions developer mode.
- Uses Manifest V3 with cookies permission scoped to linkedin.com.
- Reads li_at + JSESSIONID via chrome.cookies.get().
- Sends cookies to configurable backend URL via fetch() PUT to /api/v1/settings/linkedin.
- Shows clear status: cookies detected, sending, success, or error.
- No external dependencies -- pure vanilla HTML/CSS/JS.
</success_criteria>

<output>
After completion, create `.planning/phases/chrome-extension-linkedin-cookie-auth/chrome-extension-linkedin-cookie-auth-02-SUMMARY.md`
</output>
