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
const headless = process.env.LAUNCHBOARD_SMOKE_HEADLESS !== 'false';
const verbose = process.env.LAUNCHBOARD_SMOKE_VERBOSE === 'true';
const outputDir = path.join(repoRoot, 'test-results', 'desktop-smoke');
const uploadedResumeName = 'desktop-smoke-resume.pdf';

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

function npmCommand() {
  return process.platform === 'win32' ? 'npm.cmd' : 'npm';
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

async function prepareFixture(tempRoot) {
  const resumeSource = path.join(repoRoot, 'knowledge', 'default_resume.pdf');
  if (!(await fileExists(resumeSource))) {
    throw new Error(`Resume fixture missing at ${resumeSource}`);
  }
  const resumeTarget = path.join(tempRoot, uploadedResumeName);
  await fs.copyFile(resumeSource, resumeTarget);
  return resumeTarget;
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
  await context.tracing.start({ screenshots: true, snapshots: true, sources: true });
  const page = context.pages()[0] ?? (await context.newPage());
  return { context, page };
}

async function verifySettings(page) {
  await page.goto(`${frontendUrl}/settings`, { waitUntil: 'domcontentloaded' });
  await page.getByRole('heading', { name: 'Settings' }).waitFor();
  await page.getByText(uploadedResumeName).waitFor();
  await page.getByText('Los Angeles, CA').first().waitFor();
  const welcomeHeading = page.getByRole('heading', { name: 'Welcome to Launchboard' });
  assert.equal(await welcomeHeading.count(), 0, 'Onboarding should not reopen once the desktop workspace is established.');
}

async function waitForVisible(page, candidates, timeoutMs = 35_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    for (const candidate of candidates) {
      if (await candidate.isVisible().catch(() => false)) {
        return candidate;
      }
    }
    await page.waitForTimeout(250);
  }
  throw new Error(`Timed out waiting for one of: ${candidates.map((candidate) => candidate.toString()).join(', ')}`);
}

async function clickWhenStable(page, locator, timeoutMs = 30_000) {
  const deadline = Date.now() + timeoutMs;
  let lastError = null;

  while (Date.now() < deadline) {
    try {
      await locator.waitFor({ state: 'visible', timeout: Math.min(2_000, timeoutMs) });
      await locator.click();
      return;
    } catch (error) {
      lastError = error;
      await page.waitForTimeout(500);
    }
  }

  throw lastError || new Error(`Timed out clicking ${locator.toString()}`);
}

async function completeFirstRun(page) {
  log('Running first-launch onboarding flow');

  // The wizard now opens directly on the resume step (no welcome step) and is
  // 2 steps total (resume → search). The auto-advance to "What are you looking
  // for?" happens automatically after the resume upload analysis returns.
  await page.goto(frontendUrl, { waitUntil: 'domcontentloaded' });
  await page.getByRole('heading', { name: 'Upload Your Resume' }).waitFor();
  const resumeInput = page.getByTestId('onboarding-resume-input');
  await resumeInput.setInputFiles(process.env.LAUNCHBOARD_SMOKE_RESUME_PATH);

  const preferencesHeading = page.getByRole('heading', { name: 'What are you looking for?' });
  await preferencesHeading.waitFor({ timeout: 35_000 });

  const rolesInput = page.getByTestId('onboarding-roles-input');
  await rolesInput.fill('Data Platform Engineering Manager');
  await rolesInput.press('Enter');

  const locationInput = page.getByPlaceholder('Add a city, state, or region');
  await locationInput.fill('Los Angeles, CA');
  await page.getByRole('button', { name: 'Add' }).click();
  await page.getByText('Los Angeles, CA').first().waitFor();

  const searchResponsePromise = page.waitForResponse(
    (response) =>
      response.url() === `${apiBaseUrl}/onboarding/search` &&
      response.request().method() === 'POST',
    { timeout: 15_000 },
  ).catch(() => null);

  await clickWhenStable(page, page.getByTestId('onboarding-save-search'));
  await page.waitForURL(/\/search/, { timeout: 30_000 });
  const searchResponse = await searchResponsePromise;
  if (searchResponse) {
    assert.equal(searchResponse.status(), 200, 'Onboarding search should start successfully.');
  }
  await page.getByText('Los Angeles, CA').first().waitFor({ timeout: 15_000 });
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

    const tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), 'launchboard-desktop-smoke-'));
    const resumePath = await prepareFixture(tempRoot);
    process.env.LAUNCHBOARD_SMOKE_RESUME_PATH = resumePath;
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
        command: npmCommand(),
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
    await verifySettings(initial.page);
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
    await verifySettings(secondPass.page);
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
        ? "\nInstall the Playwright browser once with 'npm run desktop:smoke:install'."
        : '';

    console.error(`desktop-smoke: failed\n${error instanceof Error ? error.stack || error.message : String(error)}${help}`);
    console.error(formatLogs(managedProcesses));
    await cleanup();
    process.exit(1);
  }

  await cleanup();
}

await main();
