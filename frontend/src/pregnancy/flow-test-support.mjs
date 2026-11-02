import assert from 'node:assert/strict'
import * as jsx from 'react/jsx-runtime'
import { load, harness, mod, find, tick } from '../breeding/test-support.mjs'
import { animal, male, genders, types, record as breeding, snapshot, contextData, organizationId } from '../breeding/flow-test-support.mjs'
export { animal, male, genders, types, breeding, snapshot, organizationId }
export const payload = { animal_id: animal.id, breeding_id: breeding.id, diagnosis_date: '2026-10-05', expected_birth: '2027-01-01', confirmed: true, notes: null }
export const record = { ...payload, id: '00000150-1111-1111-1111-111111111111', status: 'ACTIVE' }
export const historyPath = a => `/api/pregnancies/animal/${a}/history`
export const breedingPath = a => `/api/breeding/animal/${a}/history`
export const animalPath = a => `/api/animals/${a}`
export const validation = load('../pregnancy/validation.ts', { '../breeding/validation': load('./validation.ts', {}) })
export const newProtocol = () => load('../pregnancy/create-protocol.ts', {})
export const newAbortProtocol = () => load('../pregnancy/abort-protocol.ts', {})
export function env(protocol = newProtocol(), abortProtocol = newAbortProtocol()) {
  let revision = 1, loggedIn = true
  const calls = [], queues = new Map(), listeners = new Set()
  const session = { getSessionRevision: () => revision, getSession: () => loggedIn ? { access: 'token' } : null,
    subscribeSession: fn => { listeners.add(fn); return () => listeners.delete(fn) },
    invalidateSession(_token, r) { if (r === revision) { revision++; loggedIn = false; listeners.forEach(f => f()) } } }
  const api = load('../lib/api.ts', { '../auth/session': session }, { fetch: async (path, options) => {
    calls.push({ path, ...options })
    const key = options.method ?? path, queue = queues.get(key)
    assert.ok(queue?.length || key === '/api/common/context', `Missing response ${key}`)
    const value = queue?.length ? await queue.shift()() : { data: contextData() }
    if (value instanceof Error) throw value
    return { status: value.status ?? 200, ok: (value.status ?? 200) >= 200 && (value.status ?? 200) < 300, json: async () => value.data }
  } })
  const errors = load('../lib/api-errors.ts', { './api': api })
  const service = load('../pregnancy/pregnancy.service.ts', { '../lib/api': api, '../lib/api-errors': errors, './validation': validation, '../breeding/validation': load('./validation.ts', {}) })
  const breedingService = load('./breeding.service.ts', { '../lib/api': api, '../lib/api-errors': errors, './validation': load('./validation.ts', {}) })
  const time = load('../auth/business-time.ts', {})
  const auth = load('../auth/auth.service.ts', { '../lib/api': api, './business-time': time,
    './current-context-validation': load('../auth/current-context-validation.ts', {}) })
  const h = harness(), root = harness(), Form = () => null, History = () => null
  let context = { status: 'loaded', currentOrganization: { id: organizationId }, canWrite: true }
  const refreshCurrentContext = async () => {
    const r = revision, data = await auth.getCurrentContext('token')
    if (r !== revision) throw new Error('Stale session')
    context = { ...context, currentOrganization: data.organization, canWrite: data.can_write, businessTimeLease: data.businessTimeLease }
    return data
  }
  const isCurrentOrganization = org => context.currentOrganization?.id === org
  const lease = time.createBusinessTimeLease(snapshot, performance.now(), Date.now())
  context = { ...context, businessTimeLease: lease, refreshCurrentContext, isCurrentOrganization }
  const imports = react => ({ react, 'react/jsx-runtime': jsx, '../../auth/WriteOnly': mod(() => null),
    '../../auth/current-context': { useCurrentContext: () => context }, '../../auth/session': session, '../../auth/business-time': time,
    '../../lib/api-errors': errors, '../../lib/api': api, '../../breeding/breeding.service': breedingService,
    '../pregnancy.service': service, '../create-protocol': protocol, '../abort-protocol': abortProtocol, '../validation': validation,
    './PregnancyForm': mod(Form), './PregnancyHistory': mod(History) })
  let confirmation = true
  const component = load('../pregnancy/components/Pregnancy.tsx', imports(h.react), { window: { confirm: () => confirmation } })
  const outer = load('../pregnancy/components/Pregnancy.tsx', imports(root.react))
  const props = { animal, revision, organizationId, canWrite: true, businessTimeLease: lease, refreshCurrentContext, isCurrentOrganization }
  let tree
  function render(extra = {}) { Object.assign(props, extra); tree = h.render(component.PregnancyScope, props); return tree }
  function queue(key, ...values) { queues.set(key, [...(queues.get(key) ?? []), ...values.map(v => typeof v === 'function' ? v : () => v)]) }
  function options(events = [breeding], fresh = props.animal) {
    queue(breedingPath(props.animal.id), { data: events }); queue('/api/catalogs/breeding-types', { data: types })
    queue('/api/animals/', { data: [fresh, male] }); queue('/api/catalogs/genders', { data: genders }); queue(animalPath(props.animal.id), { data: fresh })
  }
  async function ready(extra = {}, rows = []) {
    Object.assign(props, extra); context = { ...context, currentOrganization: { id: props.organizationId }, canWrite: props.canWrite, businessTimeLease: props.businessTimeLease }
    queue(historyPath(props.animal.id), { data: rows }); if (props.canWrite) options()
    render(); await tick(); render()
  }
  function prepare(rows = [], events = [breeding], fresh = props.animal) {
    queue(historyPath(props.animal.id), { data: rows }); queue(breedingPath(props.animal.id), { data: events })
    queue(animalPath(props.animal.id), { data: fresh }); queue('/api/catalogs/genders', { data: genders })
  }
  function sync(rows = [record], events = [breeding]) { queue(historyPath(props.animal.id), { data: rows }); queue(breedingPath(props.animal.id), { data: events }) }
  return { h, root, props, api, service, protocol, abortProtocol, calls, queue, options, ready, prepare, sync, render, component, Form, History, time,
    confirm: value => { confirmation = value },
    form: () => find(tree, Form), history: () => find(tree, History), tree: () => tree,
    outer: () => root.render(outer.default, { animal: props.animal }),
    context: values => { context = { ...context, ...values } },
    changeSession: (logout = false) => { revision++; loggedIn = !logout; listeners.forEach(f => f()) },
    count: method => calls.filter(c => method === 'GET' ? !c.method : c.method === method).length }
}
