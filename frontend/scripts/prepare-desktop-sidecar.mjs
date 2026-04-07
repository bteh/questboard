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

const result = spawnSync(
  python,
  [path.join(repoRoot, 'scripts', 'build_desktop_sidecar.py'), ...process.argv.slice(2)],
  {
  cwd: repoRoot,
  stdio: 'inherit',
  env: process.env,
  },
)

process.exit(result.status ?? 1)
