import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'

import ts from 'typescript'
import * as jsx from 'react/jsx-runtime'

const animalId = '11111111-1111-1111-1111-111111111111'
const vaccinationId = '22222222-2222-2222-2222-222222222222'
const record = { id: vaccinationId, animal_id: animalId, vaccine_name: ' Vacuna histórica ', application_date: '2026-01-01', next_application_date: null, dose: '1', batch: ' Lote ', veterinarian: null, notes: null, is_active: true }
const mod = (fn) => ({ __esModule: true, default: fn })
const tick = () => new Promise((resolve) => setImmediate(resolve))
function deferred() { let resolve; const promise = new Promise((done) => { resolve = done }); return { promise, resolve } }

function load(path, imports, globals = {}) {
  // Replace only Vite's environment expression; execute the real apiRequest with fake fetch.
  const source = readFileSync(new URL(path, import.meta.url), 'utf8').replace('import.meta.env.VITE_API_BASE_URL', 'undefined')
  const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } })
  const exports = {}
  runInNewContext(outputText, {
    exports, require(name) { if (name.endsWith('.css')) return {}; assert.ok(name in imports, name); return imports[name] },
    AbortController, Headers, TypeError, queueMicrotask, setInterval: () => 1, clearInterval() {},
    window: { addEventListener() {}, removeEventListener() {} }, document: { addEventListener() {}, removeEventListener() {} }, ...globals,
  })
  return exports
}

// Deterministic hook lifecycle: real handlers/effects, rerenders, dependency cleanup,
// deferred requests and unmounts. No browser or backend is contacted.
function harness() {
  const slots = []; let cursor = 0; const pending = []; const cleanups = new Map()
  const react = {
    useState(initial) { const i = cursor++; if (!(i in slots)) slots[i] = typeof initial === 'function' ? initial() : initial; return [slots[i], (value) => { slots[i] = typeof value === 'function' ? value(slots[i]) : value }] },
    useRef(initial) { const i = cursor++; if (!(i in slots)) slots[i] = { current: initial }; return slots[i] },
    useId: () => 'test',
    useCallback(fn, deps) { const i = cursor++; if (!(i in slots) || deps.some((dep, j) => dep !== slots[i].deps[j])) slots[i] = { fn, deps }; return slots[i].fn },
    useEffect(fn, deps) { const i = cursor++; if (!(i in slots) || deps.some((dep, j) => dep !== slots[i][j])) { slots[i] = deps; pending.push({ i, fn }) } },
  }
  return { react, slots, render(fn, props) { cursor = 0; const tree = fn(props); for (const { i, fn: effect } of pending.splice(0)) { cleanups.get(i)?.(); const cleanup = effect(); if (cleanup) cleanups.set(i, cleanup) } return tree }, unmount() { for (const cleanup of cleanups.values()) cleanup(); cleanups.clear() } }
}
function nodes(tree) { if (!tree || typeof tree !== 'object') return []; if (Array.isArray(tree)) return tree.flatMap(nodes); return [tree, ...nodes(tree.props?.children)] }
function text(tree) { if (tree == null || typeof tree === 'boolean') return ''; if (typeof tree !== 'object') return String(tree); if (Array.isArray(tree)) return tree.map(text).join(''); return text(tree.props?.children) }
const find = (tree, type) => nodes(tree).find((node) => node.type === type)
const button = (tree, label) => nodes(tree).find((node) => node.type === 'button' && text(node).includes(label))

function environment() {
  let revision = 1
  const calls = []; const responses = []
  const session = { getSession: () => ({ access: 'test-token' }), getSessionRevision: () => revision, invalidateSession: () => { revision++ } }
  const api = load('../lib/api.ts', { '../auth/session': session }, {
    fetch: async (path, options) => {
      calls.push({ path, ...options })
      assert.equal(options.headers.get('Authorization'), 'Bearer test-token')
      assert.ok(options.signal instanceof AbortSignal)
      assert.ok(responses.length, `No simulated response for ${path}`)
      const response = await responses.shift()()
      if (response instanceof Error) throw response
      return { status: response.status, ok: response.status >= 200 && response.status < 300, json: async () => { if (response.jsonError) throw new SyntaxError('Invalid JSON'); return response.data } }
    },
  })
  const errors = load('../lib/api-errors.ts', { './api': api })
  const validation = load('./validation.ts', { './civil-date': { vaccinationToday: () => '2026-10-05' } })
  const reconciliation = load('./reconciliation.ts', { './validation': validation })
  const service = load('./vaccinations.service.ts', { '../lib/api': api, '../lib/api-errors': errors, './validation': validation })
  return {
    session, api, errors, validation, reconciliation, service, calls,
    changeSession: () => { revision++ },
    queue: (...items) => { responses.push(...items.map((item) => typeof item === 'function' ? item : () => item)) },
    counts: () => ({ PUT: calls.filter((call) => call.method === 'PUT').length, GET: calls.filter((call) => !call.method).length }),
  }
}


export { animalId, vaccinationId, record, mod, tick, deferred, load, harness, nodes, text, find, button, environment }
