---
phase: chrome-extension-linkedin-cookie-auth
plan: 03
type: execute
wave: 2
depends_on: ["chrome-extension-linkedin-cookie-auth-01"]
files_modified:
  - frontend/src/api/settings.ts
  - frontend/src/types/settings.ts
  - frontend/src/hooks/use-settings.ts
  - frontend/src/routes/settings.tsx
  - frontend/src/components/onboarding/onboarding-wizard.tsx
autonomous: true

must_haves:
  truths:
    - "Settings page shows two auth modes: Extension (primary) with install/usage instructions, and Manual Paste (fallback) with a textarea for li_at"
    - "Settings page shows a 'Disconnect LinkedIn' button when connected that deletes the stored cookie"
    - "Settings page shows connection status with TTL expiry info (when cookie expires)"
    - "Manual paste textarea accepts li_at value and sends it to backend via PUT"
    - "Onboarding wizard LinkedIn step shows extension-first flow with manual paste fallback"
    - "Old email/password form is completely removed from settings and onboarding"
  artifacts:
    - path: "frontend/src/api/settings.ts"
      provides: "LinkedInCookieConfig, updated LinkedInStatus, disconnectLinkedIn() function"
      contains: "disconnectLinkedIn"
    - path: "frontend/src/types/settings.ts"
      provides: "LinkedInStatus type with expires_at field (if types are centralized here)"
    - path: "frontend/src/hooks/use-settings.ts"
      provides: "useDisconnectLinkedIn hook, updated useUpdateLinkedIn for cookie payload"
      contains: "useDisconnectLinkedIn"
    - path: "frontend/src/routes/settings.tsx"
      provides: "Refactored LinkedIn card with extension instructions, manual paste, disconnect button"
      contains: "Disconnect LinkedIn"
    - path: "frontend/src/components/onboarding/onboarding-wizard.tsx"
      provides: "Updated LinkedInStep with extension-first flow and manual paste fallback"
      contains: "li_at"
  key_links:
    - from: "frontend/src/routes/settings.tsx"
      to: "frontend/src/hooks/use-settings.ts"
      via: "useLinkedInStatus, useUpdateLinkedIn, useTestLinkedIn, useDisconnectLinkedIn hooks"
      pattern: "useDisconnectLinkedIn"
    - from: "frontend/src/hooks/use-settings.ts"
      to: "frontend/src/api/settings.ts"
      via: "API functions: updateLinkedInConfig, disconnectLinkedIn, testLinkedInConnection"
      pattern: "disconnectLinkedIn"
    - from: "frontend/src/api/settings.ts"
      to: "/api/v1/settings/linkedin"
      via: "apiPut (cookies), apiDelete (disconnect), apiPost (test)"
      pattern: "apiDelete.*settings/linkedin"
---

<objective>
Refactor the React frontend to replace the email/password LinkedIn form with a cookie-based auth UI featuring two modes: Chrome extension (primary) and manual paste (fallback). Add disconnect capability and TTL expiry display.

Purpose: The frontend must match the new backend API contract (cookie-based, not email/password). Users need clear instructions for the Chrome extension workflow, a manual paste fallback for those who prefer it, and the ability to disconnect LinkedIn entirely. The onboarding wizard also needs updating.

Output: Updated settings page, onboarding wizard, API client, hooks, and types -- all using cookie-based LinkedIn auth.
</objective>

<execution_context>
@/Users/briantehsayy/.claude/get-shit-done/workflows/execute-plan.md
@/Users/briantehsayy/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@frontend/src/api/settings.ts
@frontend/src/types/settings.ts
@frontend/src/hooks/use-settings.ts
@frontend/src/routes/settings.tsx
@frontend/src/components/onboarding/onboarding-wizard.tsx
@.planning/phases/chrome-extension-linkedin-cookie-auth/chrome-extension-linkedin-cookie-auth-01-SUMMARY.md
</context>

<tasks>

<task type="auto">
  <name>Task 1: Update API client, types, and hooks for cookie-based LinkedIn auth</name>
  <files>
    frontend/src/api/settings.ts
    frontend/src/types/settings.ts
    frontend/src/hooks/use-settings.ts
  </files>
  <action>
**frontend/src/types/settings.ts:**
- No LinkedIn types are currently defined here (they're in api/settings.ts). No changes needed to this file unless we want to centralize. Leave as-is.

**frontend/src/api/settings.ts:**
- Remove old `LinkedInConfig` interface (had `email` and `password`).
- Add new `LinkedInCookieConfig` interface:
  ```typescript
  export interface LinkedInCookieConfig {
    li_at: string;
    jsessionid?: string;
  }
  ```
- Update `LinkedInStatus` interface -- remove `email` field, add `expires_at`:
  ```typescript
  export interface LinkedInStatus {
    configured: boolean;
    authenticated: boolean;
    expires_at: string;  // ISO timestamp
    message: string;
  }
  ```
- Add `LinkedInDisconnectResponse` interface:
  ```typescript
  export interface LinkedInDisconnectResponse {
    success: boolean;
    message: string;
  }
  ```
- Update `updateLinkedInConfig` to accept `LinkedInCookieConfig`:
  ```typescript
  export function updateLinkedInConfig(config: LinkedInCookieConfig): Promise<LinkedInStatus> {
    return apiPut<LinkedInStatus>('/settings/linkedin', config);
  }
  ```
- Add `disconnectLinkedIn` function:
  ```typescript
  export function disconnectLinkedIn(): Promise<LinkedInDisconnectResponse> {
    return apiDelete<LinkedInDisconnectResponse>('/settings/linkedin');
  }
  ```
  Note: Check if `apiDelete` exists in `@/lib/api-client`. If not, add it there following the same pattern as `apiGet`/`apiPut`/`apiPost`. It should be: `export async function apiDelete<T>(path: string): Promise<T> { const res = await fetch(BASE_URL + path, { method: 'DELETE' }); ... }`. Check the api-client file first.
- Keep `getLinkedInStatus` and `testLinkedInConnection` unchanged (same endpoints, compatible response).

**frontend/src/hooks/use-settings.ts:**
- Update import: replace `LinkedInConfig` with `LinkedInCookieConfig` from `@/api/settings`.
- Add import for `disconnectLinkedIn` from `@/api/settings`.
- Update `useUpdateLinkedIn` hook:
  ```typescript
  export function useUpdateLinkedIn() {
    const queryClient = useQueryClient();
    return useMutation({
      mutationFn: (config: LinkedInCookieConfig) => updateLinkedInConfig(config),
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: ['settings', 'linkedin'] });
      },
    });
  }
  ```
- Add `useDisconnectLinkedIn` hook:
  ```typescript
  export function useDisconnectLinkedIn() {
    const queryClient = useQueryClient();
    return useMutation({
      mutationFn: () => disconnectLinkedIn(),
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: ['settings', 'linkedin'] });
      },
    });
  }
  ```
- Keep `useLinkedInStatus` and `useTestLinkedIn` unchanged.
  </action>
  <verify>
1. `cd frontend && npx tsc --noEmit` -- TypeScript compiles without errors.
2. `grep "LinkedInCookieConfig" frontend/src/api/settings.ts` -- new type exists.
3. `grep "disconnectLinkedIn" frontend/src/hooks/use-settings.ts` -- new hook exists.
4. `grep "LinkedInConfig" frontend/src/api/settings.ts` -- old email/password type is gone (only LinkedInCookieConfig remains).
5. `grep "email.*password" frontend/src/api/settings.ts` -- no matches in LinkedIn section.
  </verify>
  <done>
- API client exports LinkedInCookieConfig (li_at, jsessionid), updated LinkedInStatus (with expires_at), disconnectLinkedIn function.
- Hooks export useDisconnectLinkedIn mutation hook.
- useUpdateLinkedIn accepts LinkedInCookieConfig instead of old email/password config.
- No references to email/password in LinkedIn-related API or hook code.
  </done>
</task>

<task type="auto">
  <name>Task 2: Refactor settings page and onboarding wizard to cookie-based LinkedIn UI</name>
  <files>
    frontend/src/routes/settings.tsx
    frontend/src/components/onboarding/onboarding-wizard.tsx
  </files>
  <action>
**frontend/src/routes/settings.tsx -- LinkedIn card (Step 3) complete rewrite:**

Remove the old email/password form. Replace with a two-tab/two-mode LinkedIn connection card:

1. **Add imports:** `useDisconnectLinkedIn` from hooks. Add `Chrome` or `Puzzle` icon from lucide-react for the extension tab. Add `ClipboardPaste` or `Terminal` icon for manual paste tab.

2. **Add state for LinkedIn section:**
   ```typescript
   const [liAuthMode, setLiAuthMode] = useState<'extension' | 'manual'>('extension');
   const [liPasteValue, setLiPasteValue] = useState('');
   const disconnectLinkedIn = useDisconnectLinkedIn();
   ```

3. **Replace the LinkedIn card content with:**

   **When NOT connected (`!linkedInStatus?.configured`):**

   Two-tab toggle at top: "Chrome Extension" (default) | "Manual Paste"

   **Extension tab content:**
   - Numbered instructions:
     1. "Install the Launchboard Chrome extension" (with a note: "Load from `chrome-extension/` folder in developer mode")
     2. "Log into LinkedIn in your browser"
     3. "Click the extension icon and press 'Send Cookies'"
   - Info box: "The extension reads your LinkedIn session cookie and securely sends it to Launchboard. Your cookie is encrypted and stored locally."
   - A "Check Status" button that calls `testLinkedIn.mutate()` to verify if cookies arrived.

   **Manual paste tab content:**
   - Instructions: "If you prefer not to install the extension, you can paste your LinkedIn `li_at` cookie manually."
   - Expandable "How to find your li_at cookie" section with steps:
     1. "Open LinkedIn in Chrome"
     2. "Press F12 to open Developer Tools"
     3. "Go to Application tab -> Cookies -> linkedin.com"
     4. "Find the `li_at` cookie and copy its value"
   - Textarea for pasting the li_at value (monospace font, placeholder: "Paste your li_at cookie value here...").
   - "Connect LinkedIn" button that calls:
     ```typescript
     updateLinkedIn.mutate({ li_at: liPasteValue.trim() }, {
       onSuccess: () => {
         testLinkedIn.mutate(undefined, {
           onSuccess: (res) => {
             if (res.authenticated) {
               toast.success('LinkedIn connected');
             } else {
               toast.error('LinkedIn authentication failed', { description: res.message });
             }
           },
         });
       },
     });
     ```

   **When CONNECTED (`linkedInStatus?.configured`):**
   - Show green "Connected" badge (same style as existing).
   - Show expiry info: "Session expires: {formatted expires_at date}" in muted text. Format the ISO date to a human-readable relative date like "in 5 days" or absolute like "Mar 15, 2026".
   - Show "Test Connection" button to verify the cookie still works.
   - Show "Disconnect LinkedIn" button (destructive style -- red outline or similar) that calls:
     ```typescript
     disconnectLinkedIn.mutate(undefined, {
       onSuccess: () => {
         toast.success('LinkedIn disconnected');
       },
       onError: () => toast.error('Failed to disconnect'),
     });
     ```

4. **Update the step indicator logic:**
   - `linkedInDone` should now check `linkedInStatus?.configured === true` (same as before, just confirming).
   - The status badge in the card header should update accordingly.

5. **Update the `liForm` state** -- remove `{ email: '', password: '' }`, remove `handleSaveLinkedIn`. The new handlers are inline in the card content above.

**frontend/src/components/onboarding/onboarding-wizard.tsx -- LinkedInStep rewrite:**

Replace the email/password form in `LinkedInStep` with a simplified cookie-based flow:

1. **Keep the same overall structure** (icon, title, description, skip/continue buttons).

2. **Replace form content with two options:**

   **Option A (primary): Chrome Extension**
   - Brief instruction: "Use the Launchboard Chrome extension to connect in one click."
   - Three short steps (same as settings page but more concise).
   - "I've sent my cookies" button that checks status via `useLinkedInStatus` refetch.

   **Option B (secondary): Manual Paste**
   - Single textarea for li_at cookie value.
   - "Connect" button that sends the cookie.

3. **Update the `form` state** -- remove `{ email: '', password: '' }`. Add `pasteValue: string` state.

4. **Update `handleSave`** to use the new cookie config:
   ```typescript
   const handleSave = () => {
     updateLinkedIn.mutate({ li_at: pasteValue.trim() }, {
       onSuccess: () => {
         testLinkedIn.mutate(undefined, {
           onSuccess: (res) => {
             if (res.authenticated) {
               toast.success('LinkedIn connected');
               setTimeout(() => onNext(), 600);
             } else {
               toast.error('Authentication failed', { description: res.message });
             }
           },
         });
       },
     });
   };
   ```

5. **Update the `isConnected` check** to use `linkedInStatus?.configured` (same as before).

6. **Update the description text** -- remove mentions of "credentials" and "email/password". Replace with cookie-based language: "Connect your LinkedIn session for richer job data."

7. **Remove the security note about `.env`** -- replace with: "Your session cookie is encrypted and stored locally. It auto-expires after 7 days."

**Important:** Make sure to remove ALL references to `email` and `password` fields in both files. Search for `email`, `password`, `liForm`, `form.email`, `form.password` patterns and ensure none remain in LinkedIn-related code.
  </action>
  <verify>
1. `cd frontend && npx tsc --noEmit` -- TypeScript compiles without errors.
2. `grep -n "email\|password" frontend/src/routes/settings.tsx | grep -i linkedin` -- no email/password in LinkedIn section (email might still appear in LLM API key section which is fine).
3. `grep -n "email\|password" frontend/src/components/onboarding/onboarding-wizard.tsx` -- no matches.
4. `grep "useDisconnectLinkedIn\|disconnectLinkedIn" frontend/src/routes/settings.tsx` -- disconnect functionality present.
5. `grep "li_at" frontend/src/routes/settings.tsx` -- cookie paste functionality present.
6. `grep "li_at" frontend/src/components/onboarding/onboarding-wizard.tsx` -- cookie paste in onboarding.
7. `cd frontend && npm run build` -- production build succeeds.
  </verify>
  <done>
- Settings page LinkedIn card has two modes: Chrome Extension (primary) with step-by-step instructions, and Manual Paste (fallback) with textarea for li_at cookie.
- Connected state shows TTL expiry, test connection button, and "Disconnect LinkedIn" button.
- Disconnect button calls DELETE /settings/linkedin and clears state.
- Onboarding wizard LinkedInStep uses same cookie-based flow (extension-first, manual paste fallback).
- Zero references to email/password in LinkedIn-related UI code.
- TypeScript compiles and production build succeeds.
  </done>
</task>

</tasks>

<verification>
1. `cd frontend && npx tsc --noEmit` -- zero type errors.
2. `cd frontend && npm run build` -- production build succeeds.
3. `grep -rn "LINKEDIN_EMAIL\|LINKEDIN_PASSWORD\|LinkedInConfig" frontend/src/` -- only LinkedInCookieConfig, no old references.
4. All LinkedIn UI shows cookie-based auth (no email/password fields).
5. Disconnect functionality wired from button to DELETE API call to hook to API client.
</verification>

<success_criteria>
- Settings page has two LinkedIn auth modes (extension + manual paste) with clear instructions.
- Connected state shows expiry date and disconnect button.
- Manual paste accepts li_at cookie and sends to backend.
- Onboarding wizard updated with same cookie-based flow.
- All email/password references removed from frontend LinkedIn code.
- TypeScript compiles and build succeeds.
</success_criteria>

<output>
After completion, create `.planning/phases/chrome-extension-linkedin-cookie-auth/chrome-extension-linkedin-cookie-auth-03-SUMMARY.md`
</output>
