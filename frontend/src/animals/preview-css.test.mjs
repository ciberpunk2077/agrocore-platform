import assert from 'node:assert/strict'
import test from 'node:test'
import { mkdtemp, rm, readFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'

test('Vite serves nonempty preview CSS modules, with exact layout selectors and stable-write watching', async () => {
  const temporary = await mkdtemp(join(tmpdir(), 'agrocore-preview-css-'))
  const root = fileURLToPath(new URL('../../', import.meta.url))
  let server
  try {
    server = await createServer({ root, configFile: join(root, 'vite.config.ts'), mode: 'development', cacheDir: temporary,
      optimizeDeps: { noDiscovery: true, include: [] }, server: { middlewareMode: true, hmr: false } })
    const css = await server.transformRequest('/src/pages/AnimalEditPreviewPage.css')
    assert.ok(css?.code)
    assert.ok(!css.code.includes('const __vite__css = ""'))
    for (const selector of ['.animal-edit-preview__header', '.animal-preview-icon', '.animal-preview-layout', '.animal-preview-card', '.animal-preview-layout__aside', '.animal-edit-preview__footer']) assert.ok(css.code.includes(selector), selector)
    assert.ok(css.code.includes('grid-template-columns'))
    assert.ok(css.code.includes('73fr'))
    assert.ok(css.code.includes('27fr'))
    const config = server.config.server.watch.awaitWriteFinish
    assert.equal(config.stabilityThreshold, 300)
    const page = await server.transformRequest('/src/pages/AnimalEditPreviewPage.tsx')
    assert.ok(page.code.includes('/src/pages/AnimalEditPreviewPage.css'))
    const raw = await readFile(join(root, 'src/pages/AnimalEditPreviewPage.css'))
    assert.notEqual(raw.subarray(0, 3).toString('hex'), 'efbbbf')
  } finally {
    await server?.close()
    assert.ok(resolve(temporary).startsWith(resolve(tmpdir()) + sep + 'agrocore-preview-css-'))
    await rm(temporary, { recursive: true, force: true })
  }
})
