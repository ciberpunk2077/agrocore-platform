import assert from 'node:assert/strict'
import test from 'node:test'
import * as jsx from 'react/jsx-runtime'
import { load, harness, tick, deferred, nodes, mod } from '../breeding/test-support.mjs'
import { snapshot, contextData, id, organizationId, animal, types, validation, env, payload, record, animalId, animalPath, businessTime } from '../breeding/flow-test-support.mjs'

function clock(start = '2026-10-06T00:30:00Z') {
  let wall = Date.parse(start), mono = 0, sequence = 0
  const timers = new Map(), events = new Map()
  class BrowserDate extends Date {
    constructor(...args) { super(...(args.length ? args : [wall])) }
    static now() { return wall }
  }
  const globals = { Date: BrowserDate, performance: { now: () => mono },
    setTimeout(fn, ms) { const key = ++sequence; timers.set(key, { fn, at: mono + ms }); return key },
    clearTimeout(key) { timers.delete(key) },
    window: { addEventListener: (name, fn) => events.set(name, fn), removeEventListener: name => events.delete(name) },
    document: { visibilityState: 'visible', addEventListener: (name, fn) => events.set(name, fn), removeEventListener: name => events.delete(name) },
  }
  return { globals, advance(ms) { mono += ms; wall += ms }, jumpWall(ms) { wall += ms },
    fire() { for (const [key, timer] of [...timers]) if (timer.at <= mono) { timers.delete(key); timer.fn() } },
    event: name => events.get(name)?.(), timers,
  }
}

function contextEnv(start) {
  const c = clock(start), h = harness(), queue = [], calls = [], subscribers = new Set()
  let revision = 1
  const time = load('../auth/business-time.ts', {}, c.globals)
  const parser = load('../auth/current-context-validation.ts', {}, c.globals)
  class ApiError extends Error { constructor(status) { super('API'); this.status = status } }
  const api = { ApiError, async apiRequest(path, options) {
    calls.push({ path, options }); assert.ok(queue.length, 'Missing context response')
    const result = await queue.shift()()
    if (result instanceof Error) throw result
    return result
  } }
  const auth = load('../auth/auth.service.ts', { '../lib/api': api, './business-time': time, './current-context-validation': parser }, c.globals)
  const session = { getSession: () => ({ access: 'token' }), getSessionRevision: () => revision,
    subscribeSession(fn) { subscribers.add(fn); return () => subscribers.delete(fn) } }
  const Provider = load('../auth/CurrentContextProvider.tsx', { react: h.react, 'react/jsx-runtime': jsx,
    './auth.service': auth, './current-context': { CurrentContextStore: { Provider: 'store' } }, './session': session,
    './business-time': time, '../lib/api': api }, c.globals)
  let tree
  function render() { tree = h.render(Provider.default, { children: 'business read UI' }); return tree }
  const push = value => queue.push(typeof value === 'function' ? value : () => value)
  return { c, h, time, parser, auth, ApiError, calls, push, render, state: () => tree.props.value,
    changeSession() { revision++; subscribers.forEach(fn => fn()) },
  }
}

test('current context validates base contract and tolerates missing/invalid temporal extension for READ', () => {
  const parser = load('../auth/current-context-validation.ts', {})
  assert.equal(parser.isBusinessTime(snapshot), true)
  for (const bad of [undefined, null, {}, { ...snapshot, business_today: '2026-10-06' },
    { ...snapshot, effective_timezone: 'UTC-6' }, { ...snapshot, effective_timezone: ' UTC' },
    { ...snapshot, valid_until: '2026-10-06T00:32:00Z' }, { ...snapshot, valid_until: snapshot.server_now }]) {
    assert.equal(parser.parseCurrentContext({ ...contextData(), business_time: bad }).business_time, null)
  }
  assert.throws(() => parser.parseCurrentContext({ ...contextData(), current_user: {} }))
  const identity = { ...contextData(), organization: null, membership: null, role: null, can_read: false, can_write: false }
  assert.equal(parser.parseCurrentContext(identity).business_time, null)
})

for (const browserDay of ['2026-10-04T12:00:00Z', '2026-10-06T12:00:00Z']) {
  test(`browser clock ${browserDay} does not choose business_today or extend validity`, async () => {
    const e = contextEnv(browserDay); e.push(contextData()); e.render(); await tick(); e.render()
    assert.equal(e.state().data.business_time.business_today, '2026-10-05')
    assert.equal(e.time.businessTimeIsFresh(e.state().data.businessTimeLease), true)
    assert.equal(e.calls[0].options.cache, 'no-store')
    const v = load('./validation.ts', {}, e.c.globals)
    assert.equal(v.payloadError({ ...payload, date: '2026-10-05' }, animalId, e.state().data.business_time.business_today), null)
    assert.match(v.payloadError({ ...payload, date: '2026-10-06' }, animalId, e.state().data.business_time.business_today), /futura/)
    e.c.advance(60000)
    assert.equal(e.time.businessTimeIsFresh(e.state().data.businessTimeLease), false)
    e.h.unmount()
  })
}

test('lease discounts round trip and cannot be extended by setting browser clock backwards', () => {
  const c = clock(), time = load('../auth/business-time.ts', {}, c.globals)
  c.advance(1000)
  const lease = time.createBusinessTimeLease(snapshot, 0, Date.parse('2026-10-06T00:30:00Z'))
  assert.equal(lease.remainingMs, 58999)
  c.jumpWall(-86400000); c.advance(59000)
  assert.equal(time.businessTimeIsFresh(lease), false)
  assert.equal(time.createBusinessTimeLease(snapshot, 0, Date.parse('2026-10-06T00:30:00Z')), null)
})

test('open page refreshes at tenant midnight without unmounting READ UI', async () => {
  const e = contextEnv(), next = { ...snapshot, business_today: '2026-10-06', server_now: '2026-10-06T06:00:00Z', valid_until: '2026-10-06T06:01:00Z' }
  e.push(contextData(organizationId, { ...snapshot, server_now: '2026-10-06T05:59:59Z', valid_until: '2026-10-06T06:00:00Z' }))
  e.render(); await tick(); e.render()
  assert.equal(e.state().data.business_time.business_today, '2026-10-05')
  e.push(contextData(organizationId, next)); e.c.advance(1000); e.c.fire(); e.render()
  assert.equal(e.state().status, 'loaded')
  assert.equal(e.state().data.businessTimeLease, null)
  await tick(); e.render()
  assert.equal(e.state().data.business_time.business_today, '2026-10-06')
  assert.equal(e.time.businessTimeIsFresh(e.state().data.businessTimeLease), true)
  e.h.unmount(); assert.equal(e.c.timers.size, 0)
})

test('failed refresh retains READ and invalidates CREATE, explicit recovery restores lease', async () => {
  const e = contextEnv(); e.push(contextData()); e.render(); await tick(); e.render()
  e.push(new e.ApiError(503)); e.c.advance(60000); e.c.fire(); await tick(); e.render()
  assert.equal(e.state().status, 'loaded'); assert.equal(e.state().data.businessTimeLease, null)
  e.push(contextData()); await e.state().refreshCurrentContext(); e.render()
  assert.equal(e.time.businessTimeIsFresh(e.state().data.businessTimeLease), true)
  e.h.unmount()
})

test('context without temporal data remains readable but has no CREATE lease', async () => {
  const e = contextEnv(); e.push({ ...contextData(), business_time: undefined }); e.render(); await tick(); e.render()
  assert.equal(e.state().status, 'loaded'); assert.equal(e.state().data.businessTimeLease, null)
  e.h.unmount()
})

test('refreshes deduplicate and switching organization invalidates old synchronous guard', async () => {
  const e = contextEnv(); e.push(contextData()); e.render(); await tick(); e.render()
  const controls = e.state(), d = deferred(); e.push(() => d.promise)
  const first = controls.refreshCurrentContext(), second = controls.refreshCurrentContext()
  assert.equal(first, second)
  d.resolve(contextData(id(99), { ...snapshot, effective_timezone: 'UTC', business_today: '2026-10-06' }))
  await first
  assert.equal(controls.isCurrentOrganization(organizationId), false)
  assert.equal(controls.isCurrentOrganization(id(99)), true)
  e.render(); assert.equal(e.state().data.organization.id, id(99)); e.h.unmount()
})

test('session changes abort old request and discard its late response', async () => {
  const e = contextEnv(), d = deferred(); e.push(() => d.promise); e.render()
  e.push(contextData(id(99))); e.changeSession(); await tick(); e.render()
  assert.equal(e.calls[0].options.signal.aborted, true)
  d.resolve(contextData()); await tick(); e.render()
  assert.equal(e.state().data.organization.id, id(99))
  e.h.unmount()
})

test('focus/visibility revalidate without destroying business READ state', async () => {
  const e = contextEnv(); e.push(contextData()); e.render(); await tick(); e.render()
  e.push(contextData()); e.c.event('focus'); e.render(); assert.equal(e.state().data.businessTimeLease, null)
  await tick(); e.render(); assert.equal(e.time.businessTimeIsFresh(e.state().data.businessTimeLease), true)
  e.push(contextData()); e.c.event('visibilitychange'); await tick(); e.render()
  assert.equal(e.calls.length, 3); e.h.unmount()
})

function formEnv(businessToday = '2026-10-05') {
  const h = harness(), e = env(); let calls = 0
  const Form = load('./components/BreedingForm.tsx', { react: h.react, 'react/jsx-runtime': jsx,
    '../../components/FieldError': mod(() => null), '../../lib/api-errors': e.errors, '../breeding.service': e.service, '../validation': validation })
  const props = { animal, types, males: [], disabled: false, businessToday, onCreate: async () => { calls++; return false } }
  let tree
  const render = () => { tree = h.render(Form.default, props); return tree }
  const set = (name, value) => { nodes(tree).find(n => n.props?.id === name).props.onChange({ target: { value } }); render() }
  const submit = () => nodes(tree).find(n => n.type === 'form').props.onSubmit({ preventDefault() {} })
  render(); set('breeding-type', types[0].id)
  return { h, props, render, set, submit, calls: () => calls, input: () => nodes(tree).find(n => n.props?.id === 'breeding-date') }
}

test('Breeding form max and payload validation use backend day; later day update preserves draft', async () => {
  const f = formEnv(); assert.equal(f.input().props.max, '2026-10-05')
  f.set('breeding-date', '2026-10-06'); await f.submit(); assert.equal(f.calls(), 0)
  f.set('breeding-date', '2026-10-05'); await f.submit(); assert.equal(f.calls(), 1)
  f.props.businessToday = '2026-10-06'; f.render()
  assert.equal(f.input().props.max, '2026-10-06'); assert.equal(f.input().props.value, '2026-10-05')
  assert.equal(validation.payloadError({ ...payload, date: '2026-10-05' }, animalId, '2026-10-05'), null)
  assert.match(validation.payloadError({ ...payload, date: '2026-10-06' }, animalId, '2026-10-05'), /futura/)
  f.h.unmount()
})

test('Breeding CREATE rejects 06/10 before preparation and permits 05/10 once', async () => {
  const e = env(); await e.ready()
  await assert.rejects(e.form().props.onCreate({ ...payload, date: '2026-10-06' }))
  assert.equal(e.count('POST'), 0)
  const p = { ...payload, date: '2026-10-05' }, saved = { ...record, date: p.date }
  e.prepare(p); e.queue('POST', { data: saved }); e.sync([saved])
  const work = e.form().props.onCreate(p); await e.form().props.onCreate(p); await work
  assert.equal(e.count('POST'), 1); e.h.unmount()
})

for (const invalid of ['missing', 'expired', 'refresh failed', 'wrong tenant', 'read only']) {
  test(`Breeding CREATE ${invalid}: no POST, READ remains available`, async () => {
    const e = env(); await e.ready()
    if (invalid === 'missing' || invalid === 'expired') {
      const lease = invalid === 'missing' ? null : { ...e.props.businessTimeLease, remainingMs: 0 }
      e.render({ businessTimeLease: lease }); assert.equal(e.form().props.disabled, true)
      await e.form().props.onCreate(payload)
    } else {
      e.prepare()
      e.queue('/api/common/context', invalid === 'refresh failed' ? { status: 503 }
        : { data: invalid === 'wrong tenant' ? contextData(id(99)) : { ...contextData(), can_write: false, role: 'VIEWER' } })
      if (invalid === 'wrong tenant') await e.form().props.onCreate(payload)
      else await assert.rejects(e.form().props.onCreate(payload))
    }
    assert.equal(e.count('POST'), 0); assert.ok(e.history()); e.h.unmount()
  })
}

for (const refreshFails of [false, true]) {
  test(`preparation crosses valid_until; refresh failure=${refreshFails}`, async () => {
    const e = env(); await e.ready(); const d = deferred()
    e.queue(animalPath(animalId), () => d.promise)
    e.queue('/api/catalogs/breeding-types', { data: types }); e.queue('/api/catalogs/genders', { data: [{ id: animal.gender_id, code: 'F', name: 'Hembra' }] })
    let refreshes = 0
    const context = contextData()
    const fresh = { ...context, businessTimeLease: businessTime.createBusinessTimeLease(snapshot, performance.now(), Date.now()) }
    e.render({ refreshCurrentContext: async () => {
      refreshes++
      if (refreshes === 1) return { ...fresh, businessTimeLease: { ...fresh.businessTimeLease, remainingMs: 0 } }
      if (refreshFails) throw new Error('refresh failed')
      return fresh
    } })
    if (!refreshFails) { e.queue('POST', { data: record }); e.sync() }
    const work = e.form().props.onCreate(payload); await tick(); d.resolve({ data: animal })
    if (refreshFails) await assert.rejects(work)
    else await work
    assert.equal(refreshes, 2); assert.equal(e.count('POST'), refreshFails ? 0 : 1); e.h.unmount()
  })
}
