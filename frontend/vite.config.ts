import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv, type ViteDevServer } from 'vite'

export default defineConfig(async ({ mode, command }) => {
  const demo = mode === 'demo'
  const env = loadEnv(mode, process.cwd(), '')
  const target = demo ? 'http://127.0.0.1:8011' : 'http://127.0.0.1:8000'
  if (demo && ((env.VITE_API_BASE_URL && env.VITE_API_BASE_URL !== '/api') ||
    (env.DEMO_API_TARGET && env.DEMO_API_TARGET !== target))) {
    throw new Error('DEMO requires /api and http://127.0.0.1:8011.')
  }
  if (demo && command === 'serve') {
    try {
      const response = await fetch(`${target}/api/openapi.json`, { signal: AbortSignal.timeout(3000), redirect: 'error' })
      const schema = await response.json() as { paths?: Record<string, unknown> }
      if (!response.ok || !Object.keys(schema.paths ?? {}).some(path => path.endsWith('/auth/login'))) throw new Error()
    } catch { throw new Error('DEMO backend unavailable or incompatible at 127.0.0.1:8011. Start the certified D7A launcher first.') }
  }
  return {
    plugins: [react(), ...(demo ? [{ name: 'demo-loopback-only', configurePreviewServer() {
      throw new Error('Use npm run dev:demo for the certified local DEMO session.')
    }, configureServer(server: ViteDevServer) {
      if (server.config.server.host !== '127.0.0.1' || server.config.server.port !== 5174 || !server.config.server.strictPort) {
        throw new Error('DEMO requires 127.0.0.1:5174 and strictPort; CLI overrides refused.')
      }
      server.middlewares.use((req, res, next) => {
        const path = (req.url ?? '').split('?')[0]
        const method = req.method ?? 'GET'
        if (path.startsWith('/api') && !['GET', 'HEAD', 'OPTIONS'].includes(method) &&
          !(method === 'POST' && req.url === '/api/auth/login')) {
          res.statusCode = 405
          res.setHeader('Content-Type', 'application/json')
          res.end(JSON.stringify({ detail: 'DEMO: solo lectura.' }))
          return
        }
        next()
      })
    } }] : [])],
    define: { __AGROCORE_DEMO__: JSON.stringify(demo) },
    build: demo ? { outDir: 'dist-demo' } : undefined,
    server: {
      ...(demo ? { host: '127.0.0.1', port: 5174, strictPort: true, cors: false } : {}),
      // Wait for complete saves before invalidating CSS modules. Truncate/write saves
      // can otherwise be transformed while empty and retained in the dev module cache.
      watch: { awaitWriteFinish: { stabilityThreshold: 300, pollInterval: 50 } },
      proxy: { '/api': { target, changeOrigin: true } },
    },
  }
})
