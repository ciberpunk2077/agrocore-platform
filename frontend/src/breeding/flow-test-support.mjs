import assert from 'node:assert/strict'
import * as jsx from 'react/jsx-runtime'
import { mod, tick, load, harness, find } from './test-support.mjs'

export const id = n => `${String(n).padStart(8, '0')}-1111-1111-1111-111111111111`
export const animalId = id(1), organizationId = id(2)
export const genders = [{ id: id(3), code: 'F', name: 'Hembra' }, { id: id(4), code: 'M', name: 'Macho' }]
export const types = [{ id: id(5), code: 'TEST', name: 'Tipo' }, { id: id(6), code: 'UNKNOWN', name: 'Otro tipo activo' }]
export const animal = { id: animalId, internal_id: 'A', official_tag: null, electronic_tag: null, name: null,
  species_id: id(10), breed_id: id(11), gender_id: genders[0].id, status_id: id(12), species: 'Bovino', breed: 'Raza', gender: 'Hembra', status: 'Activo',
  farm_id: null, lot_id: null, farm: null, lot: null, birth_date: '2026-01-01', birth_weight: null, mother_id: null, father_id: null, notes: null, is_active: true }
export const male = { ...animal, id: id(7), gender_id: genders[1].id, gender: 'Macho', internal_id: 'M' }
export const payload = { animal_id: animalId, breeding_type_id: types[0].id, date: '2025-01-01', male_id: null, expected_birth: null, technician: '', notes: '' }
export const record = { ...payload, id: id(8) }
export const histPath = a => `/api/breeding/animal/${a}/history`
export const animalPath = a => `/api/animals/${a}`
export const validation = load('./validation.ts', {})
export const businessTime = load('../auth/business-time.ts', {})
export const snapshot = { effective_timezone: 'America/Mexico_City', business_today: '2026-10-05',
  server_now: '2026-10-06T00:30:00Z', valid_until: '2026-10-06T00:31:00Z' }
export const contextData = (organization = organizationId, time = snapshot) => ({
  user: 'operator@example.com', current_user: { id: id(90), email: 'operator@example.com', first_name: '', last_name: '' },
  organization: { id: organization, name: 'Tenant', code: 'TENANT' }, membership: { id: id(91), is_default: true },
  role: 'OPERATOR', can_read: true, can_write: true, business_time: time,
})

export function env(sharedProtocol) {
  let revision = 1, loggedIn = true
  const calls = [], queues = new Map(), listeners = new Set()
  const session = { getSessionRevision: () => revision, getSession: () => loggedIn ? { access: 'token' } : null,
    invalidateSession(_access, requestRevision) { if (requestRevision !== revision) return; revision++; loggedIn = false; listeners.forEach(fn => fn()) },
    subscribeSession: fn => { listeners.add(fn); return () => listeners.delete(fn) } }
  const api = load('../lib/api.ts', { '../auth/session': session }, { fetch: async (path, options) => {
    calls.push({ path, ...options })
    assert.ok(options.signal === undefined || options.signal instanceof AbortSignal)
    assert.equal(options.headers.get('Authorization'), 'Bearer token')
    const key = options.method ?? path
    const queue = queues.get(key)
    assert.ok(queue?.length || key === '/api/common/context', `Missing response ${key}`)
    const value = queue?.length ? await queue.shift()() : { data: contextData() }
    if (value instanceof Error) throw value
    return { status: value.status ?? 200, ok: (value.status ?? 200) >= 200 && (value.status ?? 200) < 300, json: async () => value.data }
  } })
  const errors = load('../lib/api-errors.ts', { './api': api })
  const service = load('./breeding.service.ts', { '../lib/api': api, '../lib/api-errors': errors, './validation': validation })
  const contextValidation = load('../auth/current-context-validation.ts', {})
  const authService = load('../auth/auth.service.ts', { '../lib/api': api, './current-context-validation': contextValidation, './business-time': businessTime })
  const protocol = sharedProtocol ?? load('./create-protocol.ts', {})
  const h = harness(), root = harness()
  const Form = () => null, History = () => null, WriteOnly = () => null
  let context = { status: 'loaded', currentOrganization: { id: organizationId }, canWrite: true }
  const refreshCurrentContext = async () => {
    const revisionBefore = revision, c = new AbortController()
    try {
      const data = await authService.getCurrentContext('token', c.signal)
      if (revision !== revisionBefore) throw new Error('Stale context')
      context = { ...context, currentOrganization: data.organization, canWrite: data.can_write, businessTimeLease: data.businessTimeLease }
      return data
    } finally { c.abort() }
  }
  const isCurrentOrganization = org => context.currentOrganization?.id === org
  const initialLease = businessTime.createBusinessTimeLease(snapshot, performance.now(), Date.now())
  context = { ...context, businessTimeLease: initialLease, refreshCurrentContext, isCurrentOrganization }
  const imports = react => ({ react, 'react/jsx-runtime': jsx, '../../auth/WriteOnly': mod(WriteOnly),
    '../../auth/current-context': { useCurrentContext: () => context }, '../../auth/session': session, '../../lib/api-errors': errors,
    '../../lib/api': api,
    '../../auth/business-time': businessTime,
    '../breeding.service': service, '../create-protocol': protocol, '../validation': validation, './BreedingForm': mod(Form), './BreedingHistory': mod(History) })
  const component = load('./components/Breeding.tsx', imports(h.react))
  const outer = load('./components/Breeding.tsx', imports(root.react))
  const props = { animal, revision: 1, organizationId, canWrite: true, businessTimeLease: initialLease, refreshCurrentContext, isCurrentOrganization }
  let tree
  function render(extra = {}) { Object.assign(props, extra); tree = h.render(component.BreedingScope, props); return tree }
  function queue(key, ...responses) { queues.set(key, [...(queues.get(key) ?? []), ...responses.map(v => typeof v === 'function' ? v : () => v)]) }
  function defaults(history = [], fresh = props.animal) {
    queue(histPath(props.animal.id), { data: history })
    queue('/api/catalogs/breeding-types', { data: types }); queue('/api/catalogs/genders', { data: genders })
    queue('/api/animals/', { data: [props.animal, male] }); queue(animalPath(props.animal.id), { data: fresh })
  }
  async function ready(extra, history = []) {
    if (extra) Object.assign(props, extra)
    context = { ...context, currentOrganization: { id: props.organizationId }, canWrite: props.canWrite }
    defaults(history); render(); await tick(); render()
  }
  function prepare(p = payload, fresh = props.animal, selectedMale = male, catalog = types) {
    queue(animalPath(props.animal.id), { data: fresh }); queue('/api/catalogs/breeding-types', { data: catalog }); queue('/api/catalogs/genders', { data: genders })
    if (p.male_id !== null && p.male_id !== undefined) queue(animalPath(p.male_id), { data: selectedMale })
  }
  function sync(history = [record], fresh = props.animal) { queue(histPath(props.animal.id), { data: history }); queue(animalPath(props.animal.id), { data: fresh }) }
  return { h, root, props, api, service, authService, errors, session, protocol, calls, queue, defaults, ready, prepare, sync, render, Form, History,
    component, form: () => find(tree, Form), history: () => find(tree, History), tree: () => tree,
    outer: () => root.render(outer.default, { animal: props.animal }), context: value => { context = value },
    changeSession: (logout = false) => { revision++; loggedIn = !logout; listeners.forEach(fn => fn()) },
    count: method => calls.filter(call => method === 'GET' ? !call.method : call.method === method).length }
}
