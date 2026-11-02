import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'

import ts from 'typescript'
import * as jsx from 'react/jsx-runtime'

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
    AbortController, AbortSignal, Headers, TypeError, performance, queueMicrotask, setTimeout: () => 1, clearTimeout() {}, setInterval: () => 1, clearInterval() {},
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
    useMemo(fn, deps) { const i = cursor++; if (!(i in slots) || deps.some((dep, j) => dep !== slots[i].deps[j])) slots[i] = { value: fn(), deps }; return slots[i].value },
    useEffect(fn, deps) { const i = cursor++; if (!(i in slots) || deps.some((dep, j) => dep !== slots[i][j])) { slots[i] = deps; pending.push({ i, fn }) } },
  }
  return { react, slots, render(fn, props) { cursor = 0; const tree = fn(props); for (const { i, fn: effect } of pending.splice(0)) { cleanups.get(i)?.(); const cleanup = effect(); if (cleanup) cleanups.set(i, cleanup) } return tree }, unmount() { for (const cleanup of cleanups.values()) cleanup(); cleanups.clear() } }
}
function nodes(tree) { if (!tree || typeof tree !== 'object') return []; if (Array.isArray(tree)) return tree.flatMap(nodes); return [tree, ...nodes(tree.props?.children)] }
function text(tree) { if (tree == null || typeof tree === 'boolean') return ''; if (typeof tree !== 'object') return String(tree); if (Array.isArray(tree)) return tree.map(text).join(''); return text(tree.props?.children) }
const find = (tree, type) => nodes(tree).find((node) => node.type === type)
const button = (tree, label) => nodes(tree).find((node) => node.type === 'button' && text(node).includes(label))

export { mod, tick, deferred, load, harness, nodes, text, find, button }
