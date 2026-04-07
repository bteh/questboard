import { spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const repoRoot = path.resolve(scriptDir, '..', '..')

const pythonCandidates = [
  path.join(repoRoot, '.venv', 'bin', 'python'),
  path.join(repoRoot, '.venv', 'Scripts', 'python.exe'),
]

const python = pythonCandidates.find((candidate) => existsSync(candidate))

if (!python) {
  console.error('Launchboard desktop build requires the repo virtualenv. Run `make setup` first.')
  process.exit(1)
}

function commandName(base) {
  return process.platform === 'win32' ? `${base}.cmd` : base
}

function runOrExit(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: repoRoot,
    stdio: 'inherit',
    env: process.env,
    ...options,
  })
  if (result.error) {
    console.error(`Failed to run ${command}: ${result.error.message}`)
    process.exit(1)
  }
  if (result.status !== 0) {
    process.exit(result.status ?? 1)
  }
}

const targetInfoResult = spawnSync(
  python,
  [
    '-c',
    `
import json
import platform

machine = platform.machine().lower()
system = platform.system().lower()
target_map = {
    ("darwin", "x86_64"): ("x86_64-apple-darwin", "x86_64"),
    ("darwin", "arm64"): ("aarch64-apple-darwin", "arm64"),
    ("darwin", "aarch64"): ("aarch64-apple-darwin", "arm64"),
}
tauri_target, pyinstaller_target = target_map.get((system, machine), ("", ""))
print(json.dumps({
    "tauriTarget": tauri_target,
    "pyinstallerTargetArch": pyinstaller_target,
    "pythonArch": machine,
    "system": system,
}))
`,
  ],
  {
    cwd: repoRoot,
    encoding: 'utf-8',
    env: process.env,
  },
)

if (targetInfoResult.status !== 0) {
  if (targetInfoResult.error) {
    console.error(`Failed to detect desktop build target: ${targetInfoResult.error.message}`)
  }
  if (targetInfoResult.stderr) {
    console.error(targetInfoResult.stderr.trim())
  }
  process.exit(targetInfoResult.status ?? 1)
}

const targetInfo = JSON.parse(targetInfoResult.stdout.trim())
const tauriTarget = targetInfo.tauriTarget
const pyinstallerTargetArch = targetInfo.pyinstallerTargetArch

if (tauriTarget || pyinstallerTargetArch) {
  console.log(
    `Launchboard desktop build target: ${tauriTarget || 'default'} (Python arch: ${targetInfo.pythonArch})`,
  )
}

if (tauriTarget) {
  const installedTargets = spawnSync(commandName('rustup'), ['target', 'list', '--installed'], {
    cwd: repoRoot,
    encoding: 'utf-8',
    env: process.env,
  })
  if (installedTargets.status !== 0) {
    if (installedTargets.error) {
      console.error(`Failed to inspect installed Rust targets: ${installedTargets.error.message}`)
    }
    if (installedTargets.stderr) {
      console.error(installedTargets.stderr.trim())
    }
    process.exit(installedTargets.status ?? 1)
  }
  const installed = new Set(
    installedTargets.stdout
      .split(/\r?\n/)
      .map((item) => item.trim())
      .filter(Boolean),
  )
  if (!installed.has(tauriTarget)) {
    runOrExit(commandName('rustup'), ['target', 'add', tauriTarget])
  }
}

const prepareArgs = ['run', 'desktop:prepare:sidecar', '--']
if (pyinstallerTargetArch) {
  prepareArgs.push('--target-arch', pyinstallerTargetArch)
}
runOrExit(commandName('npm'), prepareArgs, { cwd: path.join(repoRoot, 'frontend') })

const tauriArgs = ['exec', '--', 'tauri', 'build']
if (tauriTarget) {
  tauriArgs.push('--target', tauriTarget)
}
runOrExit(commandName('npm'), tauriArgs, { cwd: path.join(repoRoot, 'frontend') })
runOrExit(python, [path.join(repoRoot, 'scripts', 'verify_desktop_bundle.py')])
