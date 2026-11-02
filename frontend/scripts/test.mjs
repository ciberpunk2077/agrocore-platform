import { readdirSync } from 'node:fs'
import { join } from 'node:path'
import { spawnSync } from 'node:child_process'
function tests(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap(entry => {
    const path = join(dir, entry.name)
    return entry.isDirectory() ? tests(path) : path.endsWith('.test.mjs') ? [path] : []
  })
}
process.exit(spawnSync(process.execPath, ['--test', ...tests('src')], { stdio: 'inherit' }).status ?? 1)
