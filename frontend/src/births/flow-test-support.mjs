import assert from 'node:assert/strict'
import * as jsx from 'react/jsx-runtime'
import { load, harness, mod, find, tick } from '../breeding/test-support.mjs'
import { animal, male, genders, record as breeding, snapshot, contextData, organizationId, id } from '../breeding/flow-test-support.mjs'
export { animal, male, genders, breeding, snapshot, organizationId, id }
export const pregnancy = { id: id(150), animal_id: animal.id, breeding_id: breeding.id, diagnosis_date: '2025-02-01', expected_birth: '2026-10-05', confirmed: true, notes: null, status: 'ACTIVE' }
export const payload = { pregnancy_id: pregnancy.id, mother_id: animal.id, calf_id: null, calf_gender_id: genders[0].id, birth_date: '2026-10-05', birth_weight: '30.00', alive: true, dystocia: false, notes: null }
export const record = { ...payload, id: id(151), calf_id: id(152) }
export const calf = { ...male, id: id(152), mother_id: animal.id, birth_date: payload.birth_date, birth_weight: payload.birth_weight }
export const historyPath = a => `/api/births/animal/${a}/history`
export const pregnancyHistory = a => `/api/pregnancies/animal/${a}/history`
export const breedingHistory = a => `/api/breeding/animal/${a}/history`
export const animalPath = a => `/api/animals/${a}`
export const pregnancyPath = p => `/api/pregnancies/${p}`
export const validation = load('../births/validation.ts', { '../breeding/validation': load('./validation.ts', {}) })
export const newProtocol = () => load('../births/create-protocol.ts', {})
export function env(protocol = newProtocol()) {
  let revision = 1, loggedIn = true, confirmations = 0, changed = 0
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
    return { status: value.status ?? 200, ok: (value.status ?? 200) >= 200 && (value.status ?? 200) < 300, json: async () => { if (value.invalidJSON) throw new Error('JSON'); return value.data } }
  } })
  const errors = load('../lib/api-errors.ts', { './api': api })
  const service = load('../births/births.service.ts', { '../lib/api': api, '../lib/api-errors': errors, './validation': validation, '../breeding/validation': load('./validation.ts', {}) })
  const breedingService = load('./breeding.service.ts', { '../lib/api': api, '../lib/api-errors': errors, './validation': load('./validation.ts', {}) })
  const pregnancyService = load('../pregnancy/pregnancy.service.ts', { '../lib/api': api, '../lib/api-errors': errors,
    './validation': load('../pregnancy/validation.ts', { '../breeding/validation': load('./validation.ts', {}) }), '../breeding/validation': load('./validation.ts', {}) })
  const time = load('../auth/business-time.ts', {})
  const auth = load('../auth/auth.service.ts', { '../lib/api': api, './business-time': time, './current-context-validation': load('../auth/current-context-validation.ts', {}) })
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
  const imports = react => ({ react, 'react/jsx-runtime': jsx, '../../auth/current-context': { useCurrentContext: () => context },
    '../../auth/session': session, '../../auth/business-time': time, '../../lib/api-errors': errors, '../../lib/api': api,
    '../../breeding/breeding.service': breedingService, '../../pregnancy/pregnancy.service': pregnancyService,
    '../births.service': service, '../create-protocol': protocol, '../validation': validation, './BirthForm': mod(Form), './BirthHistory': mod(History) })
  let confirmation = true
  const component = load('../births/components/Births.tsx', imports(h.react), { window: { confirm: () => { confirmations++; return confirmation } } })
  const outer = load('../births/components/Births.tsx', imports(root.react))
  const props = { animal, revision, organizationId, canWrite: true, businessTimeLease: lease, refreshCurrentContext, isCurrentOrganization, onPregnancyChanged: () => { changed++ } }
  let tree
  function render(extra = {}) { Object.assign(props, extra); tree = h.render(component.BirthScope, props); return tree }
  function queue(key, ...values) { queues.set(key, [...(queues.get(key) ?? []), ...values.map(v => typeof v === 'function' ? v : () => v)]) }
  function options(pregnancies = [pregnancy]) {
    queue(pregnancyHistory(props.animal.id), { data: pregnancies }); queue(breedingHistory(props.animal.id), { data: [breeding] })
    queue('/api/animals/', { data: [props.animal, calf] }); queue('/api/catalogs/genders', { data: genders }); queue(animalPath(props.animal.id), { data: props.animal })
  }
  async function ready(extra = {}, rows = []) {
    Object.assign(props, extra); context = { ...context, currentOrganization: { id: props.organizationId }, canWrite: props.canWrite, businessTimeLease: props.businessTimeLease }
    queue(historyPath(props.animal.id), { data: rows }); if (props.canWrite) options()
    render(); await tick(); render()
  }
  function prepare(changes = {}, p = payload) {
    queue(pregnancyPath(p.pregnancy_id), changes.pregnancy ?? { data: pregnancy })
    queue(animalPath(props.animal.id), changes.mother ?? { data: props.animal })
    queue(historyPath(props.animal.id), changes.history ?? { data: [] })
    if (p.calf_gender_id !== null) queue('/api/catalogs/genders', changes.genders ?? { data: genders })
    if (p.calf_id !== null) queue(animalPath(p.calf_id), changes.calf ?? { data: calf })
    queue(`/api/breeding/${breeding.id}`, changes.breeding ?? { data: breeding })
    if (changes.context) queue('/api/common/context', changes.context)
  }
  function sync(rows = [record], pregnancies = [{ ...pregnancy, status: 'FINISHED' }]) {
    queue(historyPath(props.animal.id), { data: rows }); queue(pregnancyHistory(props.animal.id), { data: pregnancies })
    queue('/api/animals/', { data: [props.animal, calf] })
    for (const row of rows) if (row.calf_id) queue(animalPath(row.calf_id), { data: { ...calf, id: row.calf_id } })
  }
  return { h, root, props, api, service, protocol, calls, queue, options, ready, prepare, sync, render, component, Form, History, time,
    form: () => find(tree, Form), history: () => find(tree, History), tree: () => tree,
    confirm: v => { confirmation = v }, confirmations: () => confirmations, changed: () => changed,
    outer: () => root.render(outer.default, { animal: props.animal }), context: v => { context = { ...context, ...v } },
    changeSession: (logout = false) => { revision++; loggedIn = !logout; listeners.forEach(f => f()) },
    count: method => calls.filter(c => method === 'GET' ? !c.method : c.method === method).length }
}
