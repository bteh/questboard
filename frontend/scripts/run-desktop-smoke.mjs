import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';
import net from 'node:net';

import { chromium } from 'playwright';

const __filename = fileURLToPath(import.meta.url);
const frontendRoot = path.resolve(path.dirname(__filename), '..');
const repoRoot = path.resolve(frontendRoot, '..');
const backendRoot = path.join(repoRoot, 'backend');
const apiBaseUrl = 'http://127.0.0.1:8765/api/v1';
const frontendUrl = 'http://127.0.0.1:5173';
const headless = process.env.QUESTBOARD_SMOKE_HEADLESS !== 'false';
const verbose = process.env.QUESTBOARD_SMOKE_VERBOSE === 'true';
const outputDir = path.join(repoRoot, 'test-results', 'desktop-smoke');
const smokePlace = 'Los Angeles, CA';

function log(message) {
  console.log(`desktop-smoke: ${message}`);
}

function ringPush(buffer, line, limit = 240) {
  if (!line) return;
  buffer.push(line);
  while (buffer.length > limit) {
    buffer.shift();
  }
}

function pnpmCommand() {
  return process.platform === 'win32' ? 'pnpm.cmd' : 'pnpm';
}

async function fileExists(targetPath) {
  try {
    await fs.access(targetPath);
    return true;
  } catch {
    return false;
  }
}

async function pythonCommand() {
  const candidates = [
    path.join(repoRoot, '.venv', 'bin', 'python'),
    path.join(repoRoot, '.venv', 'Scripts', 'python.exe'),
  ];
  for (const candidate of candidates) {
    if (await fileExists(candidate)) {
      return candidate;
    }
  }
  throw new Error("Python runtime not found. Run 'make setup' first.");
}

function withSanitizedLlmEnvironment(env) {
  const next = { ...env };
  for (const key of [
    'LLM_PROVIDER',
    'LLM_BASE_URL',
    'LLM_API_KEY',
    'LLM_MODEL',
    'OPENAI_API_KEY',
    'ANTHROPIC_API_KEY',
    'GEMINI_API_KEY',
    'GOOGLE_API_KEY',
  ]) {
    delete next[key];
  }
  return next;
}

function formatLogs(processes) {
  return processes
    .map((entry) => `--- ${entry.name} ---\n${entry.logs.join('\n') || '(no output captured)'}`)
    .join('\n\n');
}

function startManagedProcess({
  name,
  command,
  args,
  cwd,
  env,
}) {
  const logs = [];
  const child = spawn(command, args, {
    cwd,
    env,
    stdio: ['ignore', 'pipe', 'pipe'],
    detached: process.platform !== 'win32',
  });

  const record = (chunk, stream) => {
    const lines = chunk
      .toString()
      .split(/\r?\n/)
      .map((line) => line.trimEnd())
      .filter(Boolean);
    for (const line of lines) {
      const entry = `[${name}:${stream}] ${line}`;
      ringPush(logs, entry);
      if (verbose) {
        console.log(entry);
      }
    }
  };

  child.stdout?.on('data', (chunk) => record(chunk, 'out'));
  child.stderr?.on('data', (chunk) => record(chunk, 'err'));

  return { name, child, logs };
}

async function stopManagedProcess(processEntry) {
  if (!processEntry) return;
  const { child } = processEntry;
  if (child.exitCode !== null || child.signalCode) return;

  if (process.platform === 'win32') {
    await new Promise((resolve) => {
      const killer = spawn('taskkill', ['/pid', String(child.pid), '/t', '/f'], { stdio: 'ignore' });
      killer.once('exit', () => resolve());
      killer.once('error', () => resolve());
    });
    return;
  }

  try {
    process.kill(-child.pid, 'SIGTERM');
  } catch {
    try {
      child.kill('SIGTERM');
    } catch {
      return;
    }
  }

  await Promise.race([
    new Promise((resolve) => child.once('exit', resolve)),
    new Promise((resolve) => setTimeout(resolve, 5_000)),
  ]);

  if (child.exitCode === null && !child.killed) {
    try {
      process.kill(-child.pid, 'SIGKILL');
    } catch {
      try {
        child.kill('SIGKILL');
      } catch {
        // Ignore final cleanup failures.
      }
    }
  }
}

async function isPortInUse(port) {
  return new Promise((resolve) => {
    const socket = net.createConnection({ host: '127.0.0.1', port });
    const finish = (inUse) => {
      socket.removeAllListeners();
      socket.destroy();
      resolve(inUse);
    };
    socket.once('connect', () => finish(true));
    socket.once('error', () => finish(false));
    socket.setTimeout(750, () => finish(false));
  });
}

async function ensurePortAvailable(port) {
  if (await isPortInUse(port)) {
    throw new Error(`Port ${port} is already in use. Run 'make stop-dev' first.`);
  }
}

async function waitForPortClosed(port, timeoutMs = 10_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (!(await isPortInUse(port))) {
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`Port ${port} did not close within ${timeoutMs}ms.`);
}

async function waitForHttp(url, timeoutMs = 45_000, predicate = null) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) {
        const body = await response.text();
        if (!predicate || predicate(body, response)) {
          return;
        }
      }
    } catch {
      // Keep polling until the deadline.
    }
    await new Promise((resolve) => setTimeout(resolve, 400));
  }
  throw new Error(`Timed out waiting for ${url}`);
}

function shortUrl(targetUrl) {
  return targetUrl.replace(apiBaseUrl, '/api/v1');
}

function attachPageMonitors(page, apiIssues, pageIssues) {
  page.on('pageerror', (error) => {
    pageIssues.push(`pageerror: ${error.stack || error.message}`);
  });
  page.on('requestfailed', (request) => {
    if (!request.url().startsWith(apiBaseUrl)) return;
    const failure = request.failure();
    if (failure?.errorText === 'net::ERR_ABORTED') {
      return;
    }
    apiIssues.push(`${request.method()} ${shortUrl(request.url())} request failed: ${failure?.errorText || 'unknown error'}`);
  });
  page.on('response', async (response) => {
    if (!response.url().startsWith(apiBaseUrl) || response.status() < 400) return;
    if (
      response.status() === 404
      && response.request().method() === 'GET'
      && /\/search\/runs\/[^/]+\/progress$/.test(response.url())
    ) {
      return;
    }
    if (
      response.status() === 401
      && response.request().method() === 'GET'
      && /\/onboarding\/state$/.test(response.url())
    ) {
      // Expected bootstrap handshake: the app probes onboarding state before
      // the workspace session is established, gets 401, bootstraps the session,
      // then retries (200). Benign, so don't flag the first probe.
      return;
    }
    let detail = '';
    try {
      detail = (await response.text()).trim();
    } catch {
      detail = '';
    }
    apiIssues.push(
      `${response.request().method()} ${shortUrl(response.url())} -> ${response.status()}${detail ? ` ${detail.slice(0, 240)}` : ''}`,
    );
  });
}

async function prepareOutputDirectory() {
  await fs.rm(outputDir, { recursive: true, force: true });
  await fs.mkdir(outputDir, { recursive: true });
}

async function launchPersistentContext(userDataDir) {
  const context = await chromium.launchPersistentContext(userDataDir, {
    headless,
    viewport: { width: 1440, height: 1100 },
    baseURL: frontendUrl,
  });
  context.setDefaultTimeout(20_000);
  // isDesktopApp() (frontend/src/lib/platform.ts) only checks that the key
  // exists on window, so an empty stub is enough to route / down the desktop
  // entry path (/start on first run, /home after) instead of the marketing
  // landing a plain browser would get.
  await context.addInitScript(() => {
    window.__TAURI_INTERNALS__ = window.__TAURI_INTERNALS__ ?? {};
  });
  await context.tracing.start({ screenshots: true, snapshots: true, sources: true });
  const page = context.pages()[0] ?? (await context.newPage());
  return { context, page };
}

async function verifyBoard(page) {
  await page.getByRole('heading', { name: 'The board' }).waitFor({ timeout: 35_000 });
  // "N live" renders only after the board's own API query answered, so this
  // is the real backend-is-serving assertion, not just a shell render.
  await page.waitForFunction(
    () => /\d+ live$/.test(document.querySelector('.qb-live')?.textContent || ''),
    undefined,
    { timeout: 35_000 },
  );
}

async function completeFirstRun(page) {
  log('Running desktop first run: /start place picker');

  // Desktop first run: / redirects to /start, which asks one question
  // ("Where are you?"). Answering routes to /board. Wait for the session
  // bootstrap to land before moving on so the board's queries carry a token.
  const bootstrapDone = page.waitForResponse(
    (response) => response.url().includes('/session/bootstrap') && response.ok(),
    { timeout: 35_000 },
  );
  await page.goto(frontendUrl, { waitUntil: 'domcontentloaded' });
  await page.waitForURL(/\/start/, { timeout: 35_000 });
  await page.getByRole('heading', { name: 'Where are you?' }).waitFor({ timeout: 35_000 });
  await bootstrapDone;

  await page.getByLabel('Your city, region, or country').fill(smokePlace);
  // Typing opens the suggestion menu; close it so nothing overlays the button.
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: /See my board/ }).click();

  await page.waitForURL(/\/board/, { timeout: 35_000 });
  await verifyBoard(page);
}

async function verifyAfterRestart(page) {
  // The onboarded flag persisted: the desktop entry goes to /home, never
  // back to /start.
  await page.goto(frontendUrl, { waitUntil: 'domcontentloaded' });
  await page.waitForURL(/\/home/, { timeout: 35_000 });
  await page.locator('.qb-lede').waitFor({ timeout: 35_000 });

  // The workspace session persisted across the runtime restart: the board
  // still renders with a live total and zero auth failures (a dead session
  // would surface as 401s, which fail the run via the API monitor).
  await page.goto(`${frontendUrl}/board`, { waitUntil: 'domcontentloaded' });
  await verifyBoard(page);
}

async function main() {
  const managedProcesses = [];
  let context = null;
  let restartedContext = null;
  const apiIssues = [];
  const pageIssues = [];

  const cleanup = async () => {
    if (restartedContext) {
      await restartedContext.close().catch(() => {});
      restartedContext = null;
    }
    if (context) {
      await context.close().catch(() => {});
      context = null;
    }
    while (managedProcesses.length > 0) {
      const entry = managedProcesses.pop();
      await stopManagedProcess(entry);
    }
  };

  process.once('SIGINT', async () => {
    await cleanup();
    process.exit(130);
  });
  process.once('SIGTERM', async () => {
    await cleanup();
    process.exit(143);
  });

  try {
    await prepareOutputDirectory();
    await ensurePortAvailable(5173);
    await ensurePortAvailable(8765);

    const tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), 'questboard-desktop-smoke-'));
    const userDataDir = path.join(tempRoot, 'browser-profile');
    const runtimeDataDir = path.join(tempRoot, 'runtime-data');
    const workspaceDir = path.join(runtimeDataDir, 'workspaces');
    const knowledgeDir = path.join(tempRoot, 'knowledge');
    const configDir = path.join(repoRoot, 'src', 'job_finder', 'config');

    const python = await pythonCommand();
    const runtimeEnv = withSanitizedLlmEnvironment({
      ...process.env,
      PYTHONPATH: '../src',
    });

    const startRuntime = () =>
      startManagedProcess({
        name: 'desktop-runtime',
        command: python,
        args: [
          '-m',
          'app.desktop_runtime',
          '--host',
          '127.0.0.1',
          '--port',
          '8765',
          '--data-dir',
          runtimeDataDir,
          '--workspace-storage-dir',
          workspaceDir,
          '--resume-dir',
          knowledgeDir,
          '--config-dir',
          configDir,
          '--dev-origin',
          frontendUrl,
        ],
        cwd: backendRoot,
        env: runtimeEnv,
      });

    managedProcesses.push(startRuntime());
    managedProcesses.push(
      startManagedProcess({
        name: 'desktop-web',
        command: pnpmCommand(),
        args: ['run', 'desktop:dev:web'],
        cwd: frontendRoot,
        env: { ...process.env, VITE_API_URL: apiBaseUrl },
      }),
    );

    log('Waiting for desktop runtime');
    await waitForHttp('http://127.0.0.1:8765/health', 45_000, (body) => body.includes('"status":"ok"'));
    log('Waiting for desktop web UI');
    await waitForHttp(frontendUrl, 45_000);

    const initial = await launchPersistentContext(userDataDir);
    context = initial.context;
    attachPageMonitors(initial.page, apiIssues, pageIssues);

    await completeFirstRun(initial.page);
    await context.tracing.stop({ path: path.join(outputDir, 'desktop-smoke-first-run-trace.zip') });
    await context.close();
    context = null;

    log('Restarting local desktop runtime to verify session persistence');
    const runtimeProcess = managedProcesses.shift();
    await stopManagedProcess(runtimeProcess);
    await waitForPortClosed(8765);

    const restartedRuntime = startRuntime();
    managedProcesses.unshift(restartedRuntime);
    await waitForHttp('http://127.0.0.1:8765/health', 45_000, (body) => body.includes('"status":"ok"'));

    const secondPass = await launchPersistentContext(userDataDir);
    restartedContext = secondPass.context;
    attachPageMonitors(secondPass.page, apiIssues, pageIssues);
    await verifyAfterRestart(secondPass.page);
    await restartedContext.tracing.stop({ path: path.join(outputDir, 'desktop-smoke-restart-trace.zip') });
    await restartedContext.close();
    restartedContext = null;

    assert.deepEqual(apiIssues, [], `Unexpected API failures during desktop smoke:\n${apiIssues.join('\n')}`);
    assert.deepEqual(pageIssues, [], `Unexpected page errors during desktop smoke:\n${pageIssues.join('\n')}`);

    log('Desktop smoke passed');
  } catch (error) {
    const activeContext = restartedContext ?? context;
    if (activeContext) {
      try {
        const page = activeContext.pages()[0];
        if (page) {
          await page.screenshot({
            path: path.join(outputDir, 'desktop-smoke-failure.png'),
            fullPage: true,
          });
        }
      } catch {
        // Ignore screenshot failures during teardown.
      }
      try {
        await activeContext.tracing.stop({ path: path.join(outputDir, 'desktop-smoke-failure-trace.zip') });
      } catch {
        // Ignore trace stop failures when the browser is already gone.
      }
    }

    const help =
      error instanceof Error && /Executable doesn't exist|browserType\.launchPersistentContext/i.test(error.message)
        ? "\nInstall the Playwright browser once with 'pnpm run desktop:smoke:install'."
        : '';

    console.error(`desktop-smoke: failed\n${error instanceof Error ? error.stack || error.message : String(error)}${help}`);
    console.error(formatLogs(managedProcesses));
    await cleanup();
    process.exit(1);
  }

  await cleanup();
}

await main();
