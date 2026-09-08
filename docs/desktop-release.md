# Desktop Release

Questboard ships as a signed, notarized macOS app that updates itself.

- `Tauri v2` for the native shell
- a bundled Python sidecar for the local runtime
- Developer ID signing + Apple notarization
- `tauri-plugin-updater` reading a signed manifest from GitHub Releases

## Cutting a release

```bash
make desktop-release
```

That one command:

1. Finds your `Developer ID Application` certificate in the keychain
2. Reads the notarization password and the updater signing key from the keychain
3. Builds the sidecar and the app, signing the sidecar itself (see below)
4. Signs the app, sends it to Apple, waits for the verdict, staples the ticket
5. Notarizes and staples the DMG separately (see below)
6. Verifies the DMG the way a stranger's Mac would, and fails if Gatekeeper objects
7. Writes `latest.json` next to the DMG

It refuses to finish on any failure rather than shipping a half-signed build.

### Three things that are easy to get wrong

**The sidecar is a resource, so Tauri never signs it.** The PyInstaller runtime
ships under `Contents/Resources/sidecars/`, outside the set of binaries Tauri
signs on its own. Notarization fails on it. `run-desktop-build.mjs` signs the
sidecars first, with the entitlements in `src-tauri/entitlements.plist` that the
PyInstaller extractor needs (`disable-library-validation`,
`allow-unsigned-executable-memory`).

**The DMG needs its own notarization.** Tauri notarizes and staples the `.app`,
then builds and signs the DMG afterwards, so the DMG carries no ticket. A
downloaded copy is rejected as `Unnotarized Developer ID` even though the app
inside is fine. The release target submits and staples the DMG too.

**Builds without the updater key must turn the archive off.** With
`createUpdaterArtifacts` on and a public key in the config, Tauri refuses to
build at all unless `TAURI_SIGNING_PRIVATE_KEY` is set. CI and dev builds have
no key, so `run-desktop-build.mjs` passes
`--config '{"bundle":{"createUpdaterArtifacts":false}}'` for them (`--config`
is a recursive merge; the rest of the bundle config survives). Only
`make desktop-release`, which reads the key from the keychain, produces the
archive.

### One-time credential setup

Three secrets live in the login keychain, never in the repo or a `.env`:

```bash
# Apple notarization (app-specific password from account.apple.com)
security add-generic-password -a YOUR_APPLE_ID -s questboard-notarize -w APP_SPECIFIC_PASSWORD

# Updater signing key (generate once; losing it means installed copies
# can never verify another update)
pnpm -C frontend exec tauri signer generate -w /tmp/qb.key -p ''
security add-generic-password -a questboard -s questboard-updater-key -w "$(cat /tmp/qb.key)"
rm /tmp/qb.key
```

The certificate comes from Xcode > Settings > Accounts > Manage Certificates >
**+** > Developer ID Application.

The first notarization of a new Apple team takes up to an hour or so because
Apple runs a one-time review. Every later one takes about two minutes.

## Publishing so the updater can see it

The app polls
`https://github.com/bteh/questboard/releases/latest/download/latest.json`,
and the landing page links to
`.../releases/latest/download/Questboard_aarch64.dmg`. Upload four files to a
release tagged `v<version>` (the release target prints the exact command):

```bash
gh release create v0.2.0 \
  frontend/src-tauri/target/*/release/bundle/dmg/Questboard_0.2.0_aarch64.dmg \
  frontend/src-tauri/target/*/release/bundle/dmg/Questboard_aarch64.dmg \
  frontend/src-tauri/target/*/release/bundle/macos/Questboard.app.tar.gz \
  frontend/src-tauri/target/*/release/bundle/dmg/latest.json
```

The versioned DMG is the record. `Questboard_aarch64.dmg` is the same file
under a name that never changes, so the landing's download link keeps working
across releases. The `.app.tar.gz` is what installed copies download;
`latest.json` points at it and carries the signature.

Upload straight from a fresh `make desktop-release`. The bundle directory is
overwritten by any later build, including unsigned dev builds, so a file
copied from it later may not be the signed one.

## The landing page

The landing is the frontend's `/` route built as static files and served by
GitHub Pages from `.github/workflows/pages.yml`, which runs on every push that
touches the frontend. It needs no backend. It lives at
`https://bteh.github.io/questboard/` for now; the workflow builds with
`--base=/questboard/` and the router reads that base, so both the assets and
the routes resolve under the sub-path. When a domain is attached later, set
the Pages custom domain and change the base to `/`.

There is no questboard.io. That domain belongs to someone else.

**The repository must be public for this to work.** Release assets on a private
repo need authentication, so the updater gets a 404 and every installed copy
silently stays on its current version.

## How updates behave

`useAppUpdate` checks four seconds after the board paints, then every six hours.
It downloads in the background and shows a small pill in the topbar only once a
new version is on disk. Clicking it shuts the backend down cleanly (it holds an
open SQLite file and a port), installs, and relaunches.

A failed check is silent on purpose: no endpoint, no network, or a
half-published release are all things the user did not ask about and cannot act
on. Updates fail closed. A manifest with a bad signature is refused and the app
keeps running the version it has.

## Version bumps

The version lives in `frontend/src-tauri/tauri.conf.json`. Tauri compares it
against the running app, so a release whose version did not change is invisible
to the updater.

## Still open

- Intel Macs. The build is Apple Silicon only; `targetInfo` in
  `run-desktop-build.mjs` already handles `x86_64`, but no Intel build ships.
- Windows and Linux. `latest.json` carries a `darwin-aarch64` entry only.
- CI signing. Releases are cut from a local machine using the login keychain.
  CI's tag-gated "Desktop macOS Bundle" job only proves the bundle builds; it
  does not sign or publish anything.
