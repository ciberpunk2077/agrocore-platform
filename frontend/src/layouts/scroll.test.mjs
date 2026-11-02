import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import { load, harness } from '../animal-movements/test-support.mjs'

function env() {
  const h = harness(), listeners = new Map(), observers = [], resizeObservers = [], calls = [], targets = new Map()
  const document = { activeElement: null, getElementById: id => targets.get(id) }
  class HTMLElement {}
  const route = { key: 'a', pathname: '/animals', search: '', hash: '', type: 'POP' }
  const main = { scrollTop: 0, scrollLeft: 0, scrollHeight: 3000, clientHeight: 500,
    scrollTo(options) { calls.push(options); this.scrollTop = Math.min(options.top, Math.max(0, this.scrollHeight-this.clientHeight)); this.scrollLeft = options.left },
    contains: target => target.inside,
    addEventListener(type, fn) { listeners.set(type, fn) }, removeEventListener(type) { listeners.delete(type) } }
  const Component = load('../layouts/MainScrollManager.tsx', {
    react: h.react, 'react-router-dom': { useLocation: () => route, useNavigationType: () => route.type },
  }, { document, HTMLElement, ResizeObserver: class {
    constructor(callback) { this.callback = callback; resizeObservers.push(this) }
    observe() { this.active = true } disconnect() { this.active = false }
  }, MutationObserver: class {
    constructor(callback) { this.callback = callback; observers.push(this) }
    observe() { this.active = true } disconnect() { this.active = false }
  } }).default
  const props = { mainRef: { current: main } }
  const render = () => h.render(Component, props)
  const scroll = (top, left = 0) => { main.scrollTop = top; main.scrollLeft = left; listeners.get('scroll')?.() }
  return { main, route, listeners, observers, calls, targets, render, scroll, document, HTMLElement, resizeObservers, unmount: h.unmount,
    navigate(key, type = 'PUSH', hash = '') { Object.assign(route, { key, type, hash, pathname: `/${key}` }); render() },
    mutate() { observers.filter(o => o.active).forEach(o => o.callback()) } }
}
test('new routes reset only MAIN and preserve scroll for backward/forward entries', () => {
  const e = env(); e.render(); e.scroll(900, 30)
  e.navigate('b'); assert.equal(e.main.scrollTop, 0)
  e.scroll(500); e.navigate('a', 'POP'); assert.equal(e.main.scrollTop, 900); assert.equal(e.main.scrollLeft, 30)
  e.navigate('b', 'POP'); assert.equal(e.main.scrollTop, 500)
})
test('restoration waits for async content rather than losing the old position on DOM clamp', () => {
  const e = env(); e.render(); e.scroll(1200)
  e.main.scrollTop = 0; e.main.scrollHeight = 500 // React commits next page's loading state before cleanup.
  e.navigate('b'); e.navigate('a', 'POP'); assert.equal(e.main.scrollTop, 0)
  e.main.scrollHeight = 3000; e.mutate(); assert.equal(e.main.scrollTop, 1200)
  assert.equal(e.observers.at(-1).active, false)
})
test('existing and asynchronously mounted anchors take precedence over saved positions', () => {
  const e = env(), events = []
  e.render(); e.scroll(700); e.navigate('b')
  e.navigate('a', 'POP', '#secci%C3%B3n')
  assert.equal(e.observers.at(-1).active, true)
  e.targets.set('sección', { inside: true, scrollIntoView: options => events.push(options) })
  e.mutate(); assert.equal(events.length, 1); assert.equal(events[0].block, 'start'); assert.equal(events[0].behavior, 'instant')
  e.mutate(); assert.equal(events.length, 1)
})
for (const event of ['wheel', 'touchstart', 'pointerdown', 'focusin', 'keydown']) test(`manual ${event} cancels pending restoration`, () => {
  const e = env(); e.render(); e.scroll(1500); e.navigate('b')
  e.main.scrollHeight = 500; e.navigate('a', 'POP')
  e.listeners.get(event)({ key: 'PageDown' }); e.main.scrollHeight = 3000; e.mutate()
  assert.equal(e.main.scrollTop, 0); assert.equal(e.observers.at(-1).active, false)
})
test('malformed or external hash does not throw or scroll outside MAIN', () => {
  const e = env(); e.render(); let called = false
  e.targets.set('bad%', { inside: false, scrollIntoView() { called = true } })
  e.navigate('b', 'PUSH', '#bad%'); e.mutate(); assert.equal(called, false)
})
test('cleanup removes observers and all listeners; remount starts a fresh history map', () => {
  const e = env(); e.render(); e.navigate('b', 'PUSH', '#pending'); e.unmount()
  assert.equal(e.listeners.size, 0); assert.ok(e.observers.every(o => !o.active))
  assert.ok(e.resizeObservers.every(o => !o.active))
  const other = env(); other.render(); assert.equal(other.main.scrollTop, 0)
})

test('shrinking viewport keeps an already focused field visible without changing focus', () => {
  const e = env(); e.render(); const calls = []
  const field = new e.HTMLElement()
  Object.assign(field, { inside: true, getBoundingClientRect: () => ({ top: 650, bottom: 690 }), scrollIntoView: options => calls.push(options) })
  e.main.getBoundingClientRect = () => ({ top: 100, bottom: 600 })
  e.document.activeElement = field; e.resizeObservers.at(-1).callback()
  assert.equal(calls.length, 1); assert.equal(calls[0].block, 'nearest'); assert.equal(calls[0].behavior, 'instant')
  assert.equal(e.document.activeElement, field)
  field.getBoundingClientRect = () => ({ top: 200, bottom: 240 }); e.resizeObservers.at(-1).callback(); assert.equal(calls.length, 1)
  field.inside = false; e.resizeObservers.at(-1).callback(); assert.equal(calls.length, 1)
})
test('authenticated CSS bounds shell height and delegates independent scroll without touching public pages', () => {
  const css = readFileSync(new URL('./AppLayout.css', import.meta.url), 'utf8')
  assert.match(css, /height: 100vh; height: 100dvh/)
  assert.match(css, /body:has\(\.app-shell\).*overflow: hidden/)
  assert.match(css, /\.app-shell__body.*min-height: 0; overflow: hidden/)
  assert.match(css, /\.app-shell__content.*min-height: 0;.*overflow-y: auto/)
  assert.match(css, /auto auto minmax\(0, 1fr\)/)
  const sidebar = readFileSync(new URL('../components/navigation/Sidebar.css', import.meta.url), 'utf8')
  assert.match(sidebar, /\.ag-sidebar--desktop.*min-height: 0; overflow-y: auto/)
  assert.match(sidebar, /\.ag-sidebar--drawer\[open\].*position: fixed.*overflow-y: auto/)
})
