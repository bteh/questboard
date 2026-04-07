# Desktop-First Plan

_Decision date: April 3, 2026_

Launchboard should move to a **desktop-first** product strategy before investing further in a public hosted SaaS.

Desktop does not mean "anything local goes." We still need a narrow, supportable AI story. The current product policy is documented in [ai-access.md](./ai-access.md).

## Ease-of-adoption principles

Desktop only helps if the app is easy to trust and easy to start.

For Launchboard, ease of adoption should mean:

- direct download with a normal installer, not a multi-step developer setup
- signed builds from the first public release
- no required hosted account just to try the product
- no required AI setup before a user can upload a resume and see value
- sensible local defaults, with AI and advanced automation layered in after first-run value
- clear release channels: stable first, experimental later
- a clear line between **supported AI connections** and **experimental research paths**

The practical implication is that the first desktop milestone should optimize for:

1. **download**
2. **open**
3. **upload resume**
4. **run first search**

before optimizing for power-user configuration.

## Why desktop first

Launchboard is strongest when it can:

- keep resumes, job data, and AI credentials on the user’s own machine
- avoid asking mainstream users to understand API billing on day one
- run browser automation and long-running job workflows locally
- ship a “download, open, upload your resume, search” flow without multi-tenant hosted complexity

For this product, desktop-first removes several problems that are harder than the product itself right now:

- hosted auth and workspace isolation
- hosted AI cost and quota enforcement
- user trust concerns around storing API keys in a hosted service
- web/worker drift and deployment coordination
- background-job reliability across hosted services

Desktop does **not** remove source-site policy risk or scraping instability. It only makes the product architecture and user trust story much simpler.

## Recommended stack

### App shell

- **Tauri v2** for the desktop shell
- keep the existing **React + Vite** frontend
- keep the existing **Python** core logic

### Local runtime

- package a **Python sidecar** for the backend/runtime
- keep SQLite + local files as the default system of record
- use OS keychain storage where possible for local AI secrets

### Why Tauri over Electron

Tauri is the better default for Launchboard because its desktop story already matches what we need:

- official support for bundling **sidecars**, including Python applications or API servers packaged with PyInstaller
- official updater plugin with signed update artifacts
- smaller desktop footprint than shipping a full Electron runtime

Official references:

- [Tauri sidecars](https://tauri.app/develop/sidecar/)
- [Tauri distribute](https://v2.tauri.app/distribute/)
- [Tauri updater](https://v2.tauri.app/plugin/updater/)
- [Tauri 2.0 Stable Release](https://tauri.app/blog/tauri-20/)

Electron is still viable, but it is not the best fit for this specific app:

- its official updater story is centered around platform-specific server/update metadata flows
- the free official `update.electronjs.org` service only applies to **macOS** and **Windows**

Reference:

- [Electron updating applications](https://www.electronjs.org/docs/latest/tutorial/updates)
- [Electron 41.0 release notes](https://www.electronjs.org/blog/electron-41-0)

## Launchboard desktop architecture

### Keep

- existing React UI
- existing FastAPI API shape where it makes local desktop development faster
- existing Python search/scoring/apply pipeline
- local SQLite and file storage
- BYO AI and local-model support

### Change

- replace “hosted product first” with **desktop product first**
- add a **desktop runtime entrypoint** that starts Launchboard locally for the Tauri shell
- collapse the current hosted web/worker concerns into a simpler local runtime model

### Recommended runtime model

Do **not** ship the hosted architecture unchanged inside a desktop app.

Instead:

1. Keep the internal separation of responsibilities in code.
2. Add a **desktop runtime entrypoint** that starts the API and local background work together for a single-user machine.
3. Treat the Tauri app as the primary user shell, with the Python runtime as an internal local service.

That means Launchboard desktop should feel like:

- open app
- upload resume
- configure preferences
- search and rank jobs
- prepare applications

without the user needing to care that a local API exists under the hood.

## Packaging best practices

### Tauri

Use Tauri’s bundle tooling for installers and signed artifacts.

Important official guidance:

- most platforms require signing
- macOS direct-download distribution requires code signing and notarization
- Tauri’s updater requires signed update artifacts and does not allow disabling signature verification

References:

- [Tauri distribute](https://v2.tauri.app/distribute/)
- [Tauri updater signing](https://v2.tauri.app/plugin/updater/)

### Python packaging

Use **PyInstaller** for the Python runtime as the first practical path.

Why:

- it produces self-contained executables
- users do not need Python installed
- it is already a common way to package Python CLI/API servers for desktop distribution

References:

- [PyInstaller operating mode](https://pyinstaller.org/en/v5.2/operating-mode.html)
- [PyInstaller usage](https://www.pyinstaller.org/en/stable/usage.html)

Important constraints from the official docs:

- PyInstaller output is **OS-specific**
- builds must be produced on each target OS
- one-file packaging is convenient, but PyInstaller notes that one-file macOS app-bundle workflows are less efficient because they unpack at runtime

For Launchboard:

- **Phase 1 recommendation:** use a PyInstaller-packaged sidecar because it is the fastest path to a working desktop release
- **Caveat:** if notarization/performance of a one-file sidecar becomes painful on macOS, move the Python runtime to a resource-bundled directory layout instead of doubling down on one-file packaging

Tauri resources can bundle extra files and directories when needed:

- [Tauri resources](https://v2.tauri.app/develop/resources/)

## Distribution strategy

### Phase 1: macOS first

Ship:

- direct-download signed macOS app
- notarized build
- manual or lightweight in-app update check

Do **not** target the Mac App Store first. Launchboard is a better fit for direct download while the product is still moving quickly.

This also matches how other open-source desktop AI tools tend to reach early adopters: direct download first, package manager distribution second, app store distribution later or never.

### Phase 2: Windows

Add:

- signed Windows installer
- passive installer update mode if using the Tauri updater

### Phase 3: Linux

Add:

- AppImage first
- native package formats later if there is real demand

## Updates

Best practice for Launchboard desktop:

- do **not** ship auto-update until signing is in place
- once signing is ready, use the Tauri updater
- publish release artifacts to GitHub Releases or another static/CDN-backed endpoint

Tauri’s docs note that:

- updater artifacts must be signed
- update endpoints are HTTPS in production
- a static `latest.json` flow is supported
- the official Tauri Action can generate the static update JSON used by CDNs/GitHub Releases

Reference:

- [Tauri updater](https://v2.tauri.app/plugin/updater/)

## Comparable projects

These projects are not identical to Launchboard, but they are useful signals for the desktop strategy.

### T3 Code

[T3 Code](https://github.com/pingdotgg/t3code) is a desktop app for coding agents.

Useful takeaways:

- it proves there is real user demand for downloadable AI-native desktop tooling
- it distributes through direct releases and package managers like `winget`, `brew`, and `AUR`
- it expects users to authenticate local AI/dev tools before use, which is acceptable for a technical audience but not the ideal first-run story for Launchboard

Reference:

- [T3 Code repository](https://github.com/pingdotgg/t3code)

### Open WebUI Desktop

[Open WebUI Desktop](https://github.com/reecelikesramen/open-webui-desktop) is a Tauri v2 desktop shell around an existing AI web app.

Useful takeaways:

- Tauri v2 is a credible path for wrapping an existing AI product into a native desktop experience
- macOS-first distribution is a common early move
- desktop-specific UX should be treated as product work, not just packaging work

Reference:

- [Open WebUI Desktop repository](https://github.com/reecelikesramen/open-webui-desktop)

### Python sidecar examples

There are now multiple public examples of Tauri v2 apps running a Python backend as a sidecar, which is the closest architectural match to Launchboard.

Useful takeaways:

- the pattern is viable
- sidecars are no longer a weird edge case
- keeping the existing Python runtime is a practical choice, not technical debt avoidance

References:

- [Example Tauri v2 app using a Python FastAPI sidecar](https://github.com/dieharders/example-tauri-v2-python-server-sidecar)
- [Tauri + FastAPI + React sidecar example](https://github.com/guilhermeprokisch/tauri-fastapi-react-app)

## Reference set

This recommendation is based primarily on current official docs and release material:

- [Tauri sidecars](https://tauri.app/develop/sidecar/)
- [Tauri updater](https://v2.tauri.app/plugin/updater/)
- [Tauri distribute](https://v2.tauri.app/distribute/)
- [Tauri resources](https://v2.tauri.app/develop/resources/)
- [Tauri 2.0 Stable Release](https://tauri.app/blog/tauri-20/)
- [Electron updating applications](https://www.electronjs.org/docs/latest/tutorial/updates)
- [Electron 41.0 release notes](https://www.electronjs.org/blog/electron-41-0)
- [PyInstaller manual](https://pyinstaller.org/en/stable/)
- [PyInstaller operating mode](https://pyinstaller.org/en/latest/operating-mode.html)
- [PyInstaller usage](https://www.pyinstaller.org/en/stable/usage.html)

## Security model for desktop

Desktop-first improves the trust model, but it still needs discipline.

Best practice:

- keep AI keys local when possible
- use OS keychain storage for saved secrets
- never store plaintext secrets in the SQLite database
- keep browser automation local to the user’s machine
- sign desktop builds before broad distribution
- treat resume data and generated application materials as local private data by default

## Open-source positioning

Desktop-first fits the open-source strategy much better than hosted-first.

The open-source message becomes:

- Launchboard is a local-first desktop app
- your resume and AI setup stay on your computer
- you can bring your own AI or use local models
- hosted is a later optional layer, not the core requirement

That is a cleaner story for early adopters and a much more realistic path than asking normal users to sign up for hosted AI infrastructure on day one.

The open-source adoption model should be:

- **normal users:** download the desktop app and use it locally
- **power users:** bring their own AI and tune advanced settings
- **contributors:** build from source and improve the local-first workflow

## Recommended implementation order

1. Create a `src-tauri/` app shell around the existing frontend.
2. Add a Python desktop runtime entrypoint for local API/background work.
3. Package the runtime as a sidecar.
4. Add a first-run desktop onboarding flow that works before advanced AI setup.
5. Ship macOS direct-download builds first.
6. Add signed updates after the installer pipeline is stable.
7. Revisit hosted mode later as an optional commercial layer.

## Current implementation status

The first implementation pass now exists in this repo:

- `frontend/src-tauri/` contains the initial Tauri v2 desktop shell
- `backend/app/desktop_runtime.py` is the local desktop runtime entrypoint
- `make desktop-dev` and `make desktop-build` are the contributor entrypoints

What is true today:

- desktop development is scaffolded
- the shell is designed to start a local runtime automatically
- local contributor flow is now concrete instead of theoretical
- a Playwright smoke harness now exercises first-run onboarding, resume upload, search start, and desktop session persistence after a local runtime restart

What is intentionally still next:

- bundling the Python runtime as a signed packaged sidecar for end-user releases
- first-run desktop onboarding polish
- signing, notarization, and updater pipeline

## What stays true even after this decision

- the current hosted-mode work was not wasted; it clarified boundaries
- the local/open-source path remains valuable
- the eventual hosted product can still exist later

But the next major product milestone should be:

**Launchboard desktop, not Launchboard SaaS.**
