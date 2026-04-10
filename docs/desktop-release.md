# Desktop Release

Launchboard now has a real desktop packaging path built around:

- `Tauri v2` for the native shell
- a bundled Python sidecar for the local runtime
- GitHub Actions workflows for native macOS bundle validation and tag-based release artifacts

This document focuses on what is automated today and what still needs credentials before it becomes a polished public release pipeline.

## Current Release Flow

Local build:

```bash
make desktop-build
```

What that does:

1. Detects the desktop target from the Python architecture in your repo `.venv`
2. Builds the Python sidecar with PyInstaller for the matching architecture
3. Builds the Tauri app for the matching Rust target
4. Verifies that the packaged app binary and packaged sidecar have the same architecture

On macOS, this means:

- `arm64` Python -> `aarch64-apple-darwin` desktop bundle
- `x86_64` Python under Rosetta -> `x86_64-apple-darwin` desktop bundle

This avoids shipping mixed-architecture app bundles.

## CI / CD

The repo now has two desktop workflows:

- [CI](/Users/briantehsayy/Desktop/launchboard/.github/workflows/ci.yml)
  - Linux scaffold check
  - macOS native bundle build and verification
- [Desktop Release](/Users/briantehsayy/Desktop/launchboard/.github/workflows/desktop-release.yml)
  - runs on tags like `v0.2.0`
  - builds a macOS app bundle and DMG
  - uploads release artifacts to GitHub

Current release artifacts:

- `Launchboard.app.zip`
- `Launchboard_*.dmg`

## Signing And Notarization

We intentionally did **not** fake code signing in this repo.

The official Tauri docs are clear that for macOS direct distribution, code signing is required and notarization is also required for distribution outside the App Store:

- [Tauri distribute docs](https://v2.tauri.app/distribute/)
- [Tauri macOS signing / notarization docs](https://v2.tauri.app/distribute/sign/macos/)

So the current state is:

- local `make desktop-build` works
- GitHub release artifacts build
- these artifacts are **not a fully production-grade macOS distribution story yet** until Apple signing credentials are wired in

That is the right tradeoff for open-source readiness: real builds now, trustable signing later.

## Updater Status

We also intentionally did **not** enable the Tauri updater plugin yet.

Official reason:

- Tauri’s updater flow depends on signed update artifacts and a public verification key
- official docs: [Updater plugin](https://v2.tauri.app/plugin/updater/)

Because we do not have the signing/notarization credentials configured yet, enabling updater now would create a half-finished release story.

So the repo is currently:

- `desktop build`: ready
- `desktop release artifacts`: ready
- `signed production macOS release`: not yet wired
- `auto-update`: intentionally deferred until signing keys exist

## GitHub Secrets To Add

The release workflow is now prepared to use these secrets if you provide them:

- `APPLE_CERTIFICATE`
  - base64-encoded `.p12` certificate
- `APPLE_CERTIFICATE_PASSWORD`
  - password used when exporting the `.p12`
- `APPLE_SIGNING_IDENTITY`
  - optional explicit signing identity
- `APPLE_API_KEY`
  - App Store Connect API key ID
- `APPLE_API_ISSUER`
  - App Store Connect issuer ID
- `APPLE_API_KEY_P8`
  - contents of the downloaded `AuthKey_<KEYID>.p8` file

Alternative notarization path if you prefer Apple ID auth instead of App Store Connect:

- `APPLE_ID`
- `APPLE_PASSWORD`
- `APPLE_TEAM_ID`

Optional:

- `APPLE_PROVIDER_SHORT_NAME`
  - useful if your Apple account belongs to multiple teams

These map directly to the official Tauri environment variable interface documented here:

- [Tauri environment variables](https://v2.tauri.app/reference/environment-variables/)
- [Tauri macOS signing / notarization](https://v2.tauri.app/distribute/sign/macos/)

## For Users Downloading Unsigned Builds

Until Apple signing credentials are configured, macOS Gatekeeper will block the app.
Users downloading an unsigned build should do one of the following after dragging
Launchboard.app to /Applications:

**Option A — Right-click workaround (easiest):**

1. Right-click (or Control-click) Launchboard.app in /Applications
2. Click "Open" from the context menu
3. Click "Open" again in the dialog that appears
4. macOS remembers this choice — subsequent launches work normally

**Option B — Terminal workaround:**

```bash
xattr -cr /Applications/Launchboard.app
```

This clears the quarantine flag. The app will launch normally after this.

**Note:** Both workarounds are standard for open-source macOS apps that aren't
signed with an Apple Developer certificate. Once signing is configured, users
won't need to do either of these.

## Tauri Signing Config

`tauri.conf.json` sets `signingIdentity: "-"` (ad-hoc signing) for local dev
builds. In CI, Tauri automatically uses the `APPLE_SIGNING_IDENTITY` environment
variable when present, overriding this value. No additional config changes are
needed once the GitHub secrets are populated.

## What You Need To Do

1. Enroll in the Apple Developer Program if you have not already.
2. Create or export a `Developer ID Application` certificate.
3. Add the GitHub secrets listed above.
4. Push a tag like `v0.2.0`.
5. Let [Desktop Release](/Users/briantehsayy/Desktop/launchboard/.github/workflows/desktop-release.yml) build and upload the artifacts.

## What I Can And Cannot Do

I can:

- prepare the repo and workflows
- validate unsigned and optionally signed build logic
- document the exact secret contract

I cannot:

- create your Apple Developer account
- export your signing certificate
- generate your App Store Connect key
- add your GitHub secrets for you

Those steps depend on your Apple account and your GitHub repository permissions.

## Next Production Step

When you are ready for polished desktop distribution, the next work should be:

1. Add Apple Developer signing + notarization credentials to the release workflow
2. Enable updater artifact signing
3. Publish a stable release feed for Tauri updater
4. Add in-app update checks

That sequence follows current Tauri guidance and avoids shipping a misleading “updater-ready” build before the signing foundation exists.
