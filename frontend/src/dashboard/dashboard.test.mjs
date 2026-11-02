import assert from 'node:assert/strict'
import test from 'node:test'
import * as jsx from 'react/jsx-runtime'
import { load, harness, tick, deferred, nodes, button, text } from '../breeding/test-support.mjs'
import { contextData } from '../breeding/flow-test-support.mjs'

const id = n => `${String(n).padStart(8, '0')}-1111-1111-1111-111111111111`
const summary = { total_animals: 8, active_animals: 6, pregnancies: 3, births_this_month: 2,
  upcoming_births: 1, vaccinations_due: 4, average_weight: '400.125' }
const upcoming = [{ animal_id: id(1), animal: 'MADRE', expected_birth: '2026-10-11' }]
const summaryPath = '/api/dashboard/summary', upcomingPath = '/api/dashboard/upcoming-births'
const validation = load('../dashboard/validation.ts', { '../breeding/validation': load('./validation.ts', {}) })
const ui = load('../ui/components.tsx', { 'react/jsx-runtime': jsx })
const presentation = load('../dashboard/presentation.ts', {})
const Icon = load('../dashboard/components/DashboardIcon.tsx', { 'react/jsx-runtime': jsx }).default
const mod = value => ({ __esModule: true, default: value })
const Link = props => jsx.jsx('a', { ...props, href: props.to })
const ShellIcon = load('../components/navigation/ShellIcon.tsx', { 'react/jsx-runtime': jsx }).default
const FollowUp = load('../dashboard/components/DashboardFollowUp.tsx', { 'react/jsx-runtime': jsx, '../../ui/components': ui, 'react-router-dom': { Link }, './DashboardIcon': mod(Icon), '../../components/navigation/ShellIcon': mod(ShellIcon) }).default
const Distribution = load('../dashboard/components/AnimalDistribution.tsx', { 'react/jsx-runtime': jsx, '../../ui/components': ui, '../presentation': presentation }).default
const Agenda = load('../dashboard/components/UpcomingBirthAgenda.tsx', { 'react/jsx-runtime': jsx, '../../ui/components': ui, '../presentation': presentation, 'react-router-dom': { Link }, './DashboardIcon': mod(Icon) }).default

function env() {
  let revision = 1, loggedIn = true, context
  const listeners = new Set(), calls = [], queues = new Map(), outer = harness()
  const isCurrentOrganization = org => loggedIn && context.currentOrganization?.id === org
  const session = { getSession: () => loggedIn ? { access: 'token' } : null, getSessionRevision: () => revision,
    subscribeSession(fn) { listeners.add(fn); return () => listeners.delete(fn) },
    invalidateSession(_access, order) { if (order === revision) { loggedIn = false; revision++; listeners.forEach(fn => fn()) } } }
  const api = load('../lib/api.ts', { '../auth/session': session }, { fetch: async (path, options) => {
    calls.push({ path, ...options })
    assert.ok(queues.get(path)?.length, `Missing response ${path}`)
    const result = await queues.get(path).shift()()
    if (result instanceof Error) throw result
    const status = result.status ?? 200
    return { status, ok: status >= 200 && status < 300, json: async () => {
      if (result.invalidJSON) throw new Error('Malformed JSON')
      return result.data
    } }
  } })
  const service = load('../dashboard/dashboard.service.ts', { '../lib/api': api, './validation': validation })
  const errors = load('../lib/api-errors.ts', { './api': api })
  const Card = load('../dashboard/components/SummaryCard.tsx', { 'react/jsx-runtime': jsx, 'react-router-dom': { Link }, '../../ui/components': ui, './DashboardIcon': mod(Icon) }).default
  const imports = react => ({ react, 'react/jsx-runtime': jsx, '../auth/current-context': { useCurrentContext: () => context },
    '../auth/useSession': { useSession: () => ({ session: session.getSession(), revision }) }, '../auth/session': session,
    '../dashboard/dashboard.service': service, '../dashboard/components/SummaryCard': { __esModule: true, default: Card },
    '../lib/api-errors': errors, '../dashboard/components/AnimalDistribution': mod(Distribution),
    '../dashboard/components/UpcomingBirthAgenda': mod(Agenda), '../dashboard/components/DashboardIcon': mod(Icon), '../dashboard/components/DashboardFollowUp': mod(FollowUp) })
  const Page = load('../pages/DashboardPage.tsx', imports(outer.react))
  let inner, Scope, key, tree, props
  function setContext(org = id(10), day = '2026-10-11', changes = {}) {
    context = { status: 'loaded', currentOrganization: { id: org }, canRead: true, canWrite: false,
      currentRole: 'VIEWER', data: { business_time: day ? { business_today: day } : null },
      businessTimeLease: {}, isCurrentOrganization, ...changes }
  }
  setContext()
  // Render new pure presentation components; preserve SummaryCard nodes for the
  // existing seven-indicator assertions. Async handlers/effects remain real.
  function presentationTree(node) {
    if (!node || typeof node !== 'object') return node
    if (Array.isArray(node)) return node.map(presentationTree)
    if (typeof node.type === 'function' && node.type !== Card) return presentationTree(node.type(node.props))
    return { ...node, props: { ...node.props, children: presentationTree(node.props?.children) } }
  }
  function render() {
    const wrapper = outer.render(Page.default, {})
    if (wrapper.type !== Page.DashboardScope) {
      inner?.unmount(); inner = null; key = null; tree = wrapper; return tree
    }
    if (!inner || key !== wrapper.key) {
      inner?.unmount(); inner = harness(); key = wrapper.key
      Scope = load('../pages/DashboardPage.tsx', imports(inner.react)).DashboardScope
    }
    props = wrapper.props
    tree = presentationTree(inner.render(Scope, props))
    return tree
  }
  const queue = (path, value) => queues.set(path, [...(queues.get(path) ?? []), typeof value === 'function' ? value : () => value])
  const pair = (s = summary, u = upcoming) => { queue(summaryPath, { data: s }); queue(upcomingPath, { data: u }) }
  const metrics = () => nodes(tree).filter(node => node.type === Card).map(node => node.props.value)
  return { calls, api, service, session, queue, pair, render, metrics, setContext, context: () => context,
    key: () => key, tree: () => tree, text: () => text(tree),
    async ready(s = summary, u = upcoming) { pair(s, u); render(); await tick(); return render() },
    changeSession(logout = false) { revision++; loggedIn = !logout; listeners.forEach(fn => fn()) },
    unmount() { inner?.unmount(); outer.unmount() },
  }
}

test('summary runtime accepts all indicators, decimal string and null without coercion', () => {
  assert.equal(validation.isDashboardSummary(summary), true)
  for (const value of [null, '0', '400.125', '12345678901234567890.123456789']) {
    assert.equal(validation.isDashboardSummary({ ...summary, average_weight: value }), true)
  }
})
for (const key of ['total_animals', 'active_animals', 'pregnancies', 'births_this_month', 'upcoming_births', 'vaccinations_due']) {
  test(`summary rejects invalid, negative and missing ${key}`, () => {
    for (const value of [-1, 1.5, '1', null, undefined, NaN, Infinity, Number.MAX_SAFE_INTEGER + 1]) {
      assert.equal(validation.isDashboardSummary({ ...summary, [key]: value }), false)
    }
    const incomplete = { ...summary }; delete incomplete[key]
    assert.equal(validation.isDashboardSummary(incomplete), false)
  })
}
test('summary rejects incompatible structures and invalid decimal', () => {
  for (const value of [null, [], {}, false, 'summary']) assert.equal(validation.isDashboardSummary(value), false)
  for (const value of [undefined, 400, '', ' ', 'NaN', 'Infinity', '1e3', '1,23', '12kg', '.', '+']) {
    assert.equal(validation.isDashboardSummary({ ...summary, average_weight: value }), false)
  }
})
test('upcoming validates UUID, nonempty label and exact civil dates including leap years', () => {
  assert.equal(validation.isUpcomingBirths(upcoming), true)
  assert.equal(validation.isUpcomingBirths([]), true)
  assert.equal(validation.isUpcomingBirths([{ ...upcoming[0], expected_birth: '2024-02-29' }]), true)
  for (const value of [null, {}, 'list', [null], [{}]]) assert.equal(validation.isUpcomingBirths(value), false)
  for (const changes of [{ animal_id: 'bad' }, { animal_id: null }, { animal: null }, { animal: '' }, { animal: ' ' },
    { expected_birth: '2026-02-29' }, { expected_birth: '2026-04-31' }, { expected_birth: '0000-01-01' },
    { expected_birth: '2026-1-1' }, { expected_birth: '2026-10-11T00:00:00Z' }, { expected_birth: undefined }]) {
    assert.equal(validation.isUpcomingBirths([{ ...upcoming[0], ...changes }]), false)
  }
  for (const key of ['animal_id', 'animal', 'expected_birth']) {
    const row = { ...upcoming[0] }; delete row[key]
    assert.equal(validation.isUpcomingBirths([row]), false)
  }
})
test('real HTTP service uses GET no-store bearer and shared AbortSignal', async () => {
  const e = env(), c = new AbortController()
  e.pair()
  assert.equal(await e.service.getDashboardSummary('token', c.signal), summary)
  assert.equal(await e.service.getUpcomingBirths('token', c.signal), upcoming)
  for (const call of e.calls) {
    assert.equal(call.method, 'GET'); assert.equal(call.cache, 'no-store')
    assert.equal(call.signal, c.signal); assert.equal(call.headers.get('Authorization'), 'Bearer token')
    assert.equal(call.body, undefined)
  }
})
for (const endpoint of ['summary', 'upcoming']) {
  test(`real service rejects malformed JSON, incomplete data and unexpected status: ${endpoint}`, async () => {
    const e = env(), path = endpoint === 'summary' ? summaryPath : upcomingPath
    const read = endpoint === 'summary' ? e.service.getDashboardSummary : e.service.getUpcomingBirths
    for (const value of [{ invalidJSON: true }, { data: {} }, { data: null }, { status: 202, data: endpoint === 'summary' ? summary : upcoming }]) {
      e.queue(path, value); await assert.rejects(read('token'))
    }
  })
}
test('initial loading then validated indicators preserves labels and date/window', async () => {
  const e = env(), s = deferred(), u = deferred()
  e.queue(summaryPath, () => s.promise); e.queue(upcomingPath, () => u.promise)
  e.render(); assert.match(e.text(), /Cargando Dashboard/); assert.deepEqual(e.metrics(), [])
  s.resolve({ data: summary }); await tick(); e.render(); assert.deepEqual(e.metrics(), [])
  u.resolve({ data: upcoming }); await tick(); e.render()
  assert.deepEqual(e.metrics(), [8, 6, 3, 2, 1, 4, '400.125 kg'])
  assert.match(e.text(), /Fecha operativa del contexto: 2026-10-11/)
  assert.match(e.text(), /30 días, inclusive/); assert.match(e.text(), /MADRE/)
  assert.equal(nodes(e.tree()).filter(n => n.type === 'button').length, 1)
})
test('empty shows zero indicators, Sin datos and no upcoming births', async () => {
  const e = env(); await e.ready({ ...summary, total_animals: 0, active_animals: 0, pregnancies: 0,
    births_this_month: 0, upcoming_births: 0, vaccinations_due: 0, average_weight: null }, [])
  assert.deepEqual(e.metrics(), [0, 0, 0, 0, 0, 0, 'Sin datos'])
  assert.match(e.text(), /No hay próximos nacimientos/)
})
for (const failed of [summaryPath, upcomingPath]) {
  test(`failure of ${failed} cancels sibling, publishes no partial data and retries only manually`, async () => {
    const e = env(), late = deferred()
    e.queue(failed, { status: 503 }); e.queue(failed === summaryPath ? upcomingPath : summaryPath, () => late.promise)
    e.render(); await tick(); e.render()
    assert.match(e.text(), /No fue posible/); assert.deepEqual(e.metrics(), [])
    assert.ok(e.calls.every(c => c.signal.aborted)); assert.equal(e.calls.length, 2)
    late.resolve({ data: failed === summaryPath ? upcoming : summary }); await tick(); e.render()
    e.setContext(id(10), '2026-10-11', { businessTimeLease: { renewed: true } }); e.render(); await tick()
    assert.equal(e.calls.length, 2)
    e.pair(); button(e.tree(), 'Reintentar').props.onClick(); e.render(); await tick(); e.render()
    assert.equal(e.calls.length, 4); assert.equal(e.metrics()[0], 8)
  })
}
test('manual refresh clears prior pair, starts a fresh scope and can supersede pending load', async () => {
  const e = env(); await e.ready()
  const action = button(e.tree(), 'Actualizar').props.onClick, late = deferred()
  e.queue(summaryPath, () => late.promise); e.queue(upcomingPath, () => late.promise)
  action(); e.render(); assert.deepEqual(e.metrics(), [])
  e.pair({ ...summary, total_animals: 99 }, [])
  action(); await tick(); e.render()
  assert.ok(e.calls.slice(2, 4).every(c => c.signal.aborted)); assert.equal(e.metrics()[0], 99)
  late.resolve({ data: {} }); await tick(); e.render(); assert.equal(e.metrics()[0], 99)
})
test('organization A to B clears indicators immediately and loads B', async () => {
  const e = env(); await e.ready()
  e.setContext(id(20)); e.pair({ ...summary, total_animals: 20 }); e.render()
  assert.deepEqual(e.metrics(), []); await tick(); e.render(); assert.equal(e.metrics()[0], 20)
})
test('A to B to A rejects old A response despite identical organization and revision', async () => {
  const e = env(), old = deferred()
  e.queue(summaryPath, () => old.promise); e.queue(upcomingPath, { data: upcoming }); e.render()
  await tick()
  const firstKey = e.key()
  e.setContext(id(20)); e.pair({ ...summary, total_animals: 20 }); e.render(); await tick(); e.render()
  e.setContext(id(10)); e.pair({ ...summary, total_animals: 30 }); e.render(); await tick(); e.render()
  assert.equal(e.key(), firstKey); assert.ok(e.calls[0].signal.aborted)
  old.resolve({ data: { ...summary, total_animals: 100 } }); await tick(); e.render()
  assert.equal(e.metrics()[0], 30)
})
test('A to B to A ignores late error and stale refresh handler from original instance', async () => {
  const e = env(); await e.ready()
  const staleRefresh = button(e.tree(), 'Actualizar').props.onClick, old = deferred()
  e.queue(summaryPath, () => old.promise); e.queue(upcomingPath, { data: upcoming })
  staleRefresh(); await tick()
  e.setContext(id(20)); e.pair({ ...summary, total_animals: 20 }); e.render(); await tick(); e.render()
  e.setContext(id(10)); e.pair({ ...summary, total_animals: 30 }); e.render(); await tick(); e.render()
  const count = e.calls.length
  staleRefresh(); assert.equal(e.calls.length, count)
  old.resolve(new Error('Late old A error')); await tick(); e.render()
  assert.equal(e.metrics()[0], 30); assert.equal(nodes(e.tree()).some(n => n.props.role === 'alert'), false)
})
test('unmount before scheduled initial load makes no request', async () => {
  const e = env(); e.render(); e.unmount(); await tick()
  assert.equal(e.calls.length, 0)
})
test('malformed pair enters recoverable error without replacing values with zero', async () => {
  const e = env(); e.queue(summaryPath, { invalidJSON: true }); e.queue(upcomingPath, { data: upcoming })
  e.render(); await tick(); e.render()
  assert.deepEqual(e.metrics(), []); assert.ok(button(e.tree(), 'Reintentar'))
  assert.equal(e.calls.length, 2)
})
test('READ remains usable without temporal extension and displays unavailability', async () => {
  const e = env(); e.setContext(id(10), null); await e.ready()
  assert.equal(e.metrics()[0], 8); assert.match(e.text(), /Fecha operativa no disponible/)
})
for (const kind of ['success', 'error']) {
  test(`unmount aborts and rejects late ${kind}`, async () => {
    const e = env(), old = deferred()
    e.queue(summaryPath, () => old.promise); e.queue(upcomingPath, { data: upcoming }); e.render()
    await tick()
    const before = e.tree(); e.unmount(); assert.ok(e.calls.every(c => c.signal.aborted))
    old.resolve(kind === 'error' ? new Error('late') : { data: summary }); await tick()
    assert.equal(e.tree(), before)
  })
  test(`session revision aborts immediately and rejects late ${kind}`, async () => {
    const e = env(), old = deferred()
    e.queue(summaryPath, () => old.promise); e.queue(upcomingPath, { data: upcoming }); e.render()
    await tick()
    e.changeSession(); assert.ok(e.calls.every(c => c.signal.aborted))
    e.pair({ ...summary, total_animals: 50 }); e.render(); await tick(); e.render()
    old.resolve(kind === 'error' ? new Error('late') : { data: summary }); await tick(); e.render()
    assert.equal(e.metrics()[0], 50)
  })
}
test('organization guard rejects completion even before React renders new context', async () => {
  const e = env(), old = deferred()
  e.queue(summaryPath, () => old.promise); e.queue(upcomingPath, { data: upcoming }); e.render()
  await tick()
  e.setContext(id(20)); old.resolve({ data: summary }); await tick()
  e.pair({ ...summary, total_animals: 20 }); e.render()
  assert.deepEqual(e.metrics(), []); await tick(); e.render(); assert.equal(e.metrics()[0], 20)
})
test('business_today change creates new reads; lease expiry and same-day renewal do not', async () => {
  const e = env(); await e.ready(); const originalKey = e.key()
  e.setContext(id(10), '2026-10-11', { businessTimeLease: null }); e.render()
  e.setContext(id(10), '2026-10-11', { businessTimeLease: { renewed: true } }); e.render()
  assert.equal(e.calls.length, 2); assert.equal(e.key(), originalKey)
  e.setContext(id(10), '2026-10-12'); e.pair({ ...summary, births_this_month: 9 }); e.render()
  assert.notEqual(e.key(), originalKey); assert.deepEqual(e.metrics(), [])
  await tick(); e.render(); assert.equal(e.metrics()[3], 9); assert.equal(e.calls.length, 4)
  assert.match(e.text(), /2026-10-12/)
  assert.match(e.text(), /Hace 1 día/)
})
test('VIEWER reads and refreshes using only GET without write controls', async () => {
  const e = env(); await e.ready(); e.pair(); button(e.tree(), 'Actualizar').props.onClick()
  await tick(); e.render()
  assert.equal(e.calls.length, 4); assert.ok(e.calls.every(c => c.method === 'GET'))
  assert.doesNotMatch(e.text(), /Crear|Guardar|Eliminar/)
})
test('missing READ scope or logged out session does not make requests', () => {
  const e = env(); e.setContext(id(10), null, { canRead: false }); e.render()
  assert.match(e.text(), /No tienes acceso/); assert.equal(e.calls.length, 0)
  e.changeSession(true); e.render(); assert.equal(e.calls.length, 0)
})
test('403 is normalized; 401 uses shared session invalidation', async () => {
  const e = env(); e.queue(summaryPath, { status: 403, data: { detail: 'Acceso denegado' } })
  e.queue(upcomingPath, { data: [] }); e.render(); await tick(); e.render()
  assert.match(e.text(), /Acceso denegado/)
  e.queue(summaryPath, { status: 401 }); e.queue(upcomingPath, { data: [] })
  button(e.tree(), 'Reintentar').props.onClick(); await tick(); e.render()
  assert.equal(e.session.getSession(), null); assert.deepEqual(e.metrics(), [])
})

test('visual panels publish only the complete pair and clear during refresh', async () => {
  const e = env(), pending = deferred()
  e.queue(summaryPath, { data: summary }); e.queue(upcomingPath, () => pending.promise)
  e.render(); await tick(); e.render()
  assert.doesNotMatch(e.text(), /Distribución de animales|Agenda|MADRE/)
  pending.resolve({ data: upcoming }); await tick(); e.render()
  assert.match(e.text(), /Distribución de animales/); assert.match(e.text(), /Otros estados/)
  assert.match(e.text(), /75 %/); assert.match(e.text(), /MADRE/)
  const refreshPair = deferred()
  e.queue(summaryPath, () => refreshPair.promise); e.queue(upcomingPath, () => refreshPair.promise)
  button(e.tree(), 'Actualizar').props.onClick(); e.render()
  assert.doesNotMatch(e.text(), /Distribución de animales|MADRE/)
  assert.equal(button(e.tree(), 'Actualizar').props.disabled, true)
  e.unmount()
})

test('loaded Dashboard retains all seven KPI labels and uses only actual summary fields', async () => {
  const e = env(); await e.ready()
  const cards = nodes(e.tree()).filter(n => 'value' in n.props && 'label' in n.props)
  assert.deepEqual(cards.map(n => n.props.label), ['Total de animales', 'Animales activos', 'Gestaciones',
    'Nacimientos este mes', 'Próximos nacimientos', 'Vacunaciones pendientes', 'Peso promedio'])
  assert.equal(cards.length, 7)
  assert.deepEqual(cards.map(n => n.props.icon), ['herd', 'active', 'pregnancy', 'birth', 'calendar', 'vaccination', 'weight'])
  assert.doesNotMatch(e.text(), /mes anterior|tendencia|variación/)
  e.unmount()
})

test('real CurrentContextProvider renews midnight snapshot and refreshes Dashboard once', async () => {
  const e = env(), provider = harness(), timers = new Map()
  let wall = Date.parse('2026-10-06T05:59:59Z'), mono = 0, sequence = 0
  class BrowserDate extends Date { static now() { return wall } }
  const globals = { Date: BrowserDate, performance: { now: () => mono },
    setTimeout(fn) { const key = ++sequence; timers.set(key, fn); return key },
    clearTimeout(key) { timers.delete(key) } }
  const time = load('../auth/business-time.ts', {}, globals)
  const parser = load('../auth/current-context-validation.ts', {}, globals)
  const auth = load('../auth/auth.service.ts', { '../lib/api': e.api,
    './business-time': time, './current-context-validation': parser }, globals)
  const Provider = load('../auth/CurrentContextProvider.tsx', { react: provider.react, 'react/jsx-runtime': jsx,
    './auth.service': auth, './current-context': { CurrentContextStore: { Provider: 'store' } },
    './session': e.session, './business-time': time, '../lib/api': e.api }, globals)
  const first = { effective_timezone: 'America/Mexico_City', business_today: '2026-10-05',
    server_now: '2026-10-06T05:59:59Z', valid_until: '2026-10-06T06:00:00Z' }
  const next = { ...first, business_today: '2026-10-06', server_now: first.valid_until,
    valid_until: '2026-10-06T06:01:00Z' }
  const data = snapshot => ({ ...contextData(id(10), snapshot), role: 'VIEWER', can_write: false })
  function publish() {
    const value = provider.render(Provider.default, { children: 'Dashboard' }).props.value
    assert.equal(value.status, 'loaded')
    e.setContext(value.data.organization.id, value.data.business_time.business_today, {
      data: value.data, businessTimeLease: value.data.businessTimeLease, isCurrentOrganization: value.isCurrentOrganization,
    })
    return value
  }
  e.queue('/api/common/context', { data: data(first) })
  provider.render(Provider.default, { children: 'Dashboard' }); await tick()
  assert.ok(publish().data.businessTimeLease)
  await e.ready(); const oldKey = e.key()
  wall += 1000; mono += 1000
  e.queue('/api/common/context', { data: data(next) })
  const renewal = [...timers.values()]; timers.clear(); renewal.forEach(fn => fn())
  assert.equal(publish().data.businessTimeLease, null)
  e.render(); assert.equal(e.key(), oldKey)
  await tick(); assert.ok(publish().data.businessTimeLease)
  e.pair({ ...summary, births_this_month: 12 }); e.render()
  assert.notEqual(e.key(), oldKey); assert.deepEqual(e.metrics(), [])
  await tick(); e.render(); assert.equal(e.metrics()[3], 12)
  const dashboardCalls = () => e.calls.filter(call => call.path !== '/api/common/context')
  assert.equal(dashboardCalls().length, 4)
  wall += 60000; mono += 60000
  e.queue('/api/common/context', { data: data({ ...next, server_now: next.valid_until, valid_until: '2026-10-06T06:02:00Z' }) })
  const sameDay = [...timers.values()]; timers.clear(); sameDay.forEach(fn => fn())
  await tick(); publish(); e.render(); await tick()
  assert.equal(dashboardCalls().length, 4)
  assert.ok(e.calls.every(call => !call.method || call.method === 'GET'))
  e.unmount(); provider.unmount(); assert.equal(timers.size, 0)
})

test('only the four supported KPI expose drilldown targets without extra dashboard requests', async () => {
  const e = env(); await e.ready()
  const links = nodes(e.tree()).filter(n => n.props?.to?.startsWith('/dashboard/')).map(n => n.props.to)
  assert.deepEqual(links, ['/dashboard/pregnancies', '/dashboard/births_this_month', '/dashboard/upcoming_births', '/dashboard/vaccinations_due'])
  assert.equal(e.calls.length, 2)
})
