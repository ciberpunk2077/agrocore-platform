import assert from 'node:assert/strict'
import * as jsx from 'react/jsx-runtime'
import { mod, tick, deferred, load, harness, nodes, text, find, button } from './test-support.mjs'

const id = n => `${String(n).padStart(8, '0')}-1111-1111-1111-111111111111`
const animalId = id(1), organizationId = id(2), statusId = id(3)
const types = ['TRANSFER', 'ENTRY', 'PURCHASE', 'EXIT', 'SALE'].map((code, i) => ({ id: id(10+i), code, name: code }))
const farm = n => ({ id: id(n), farm_type_id: id(30), name: `Farm ${n}`, code: `${n}`, farm_type: 'Rancho', description: '', address: '', city: '', state: '', country: '' })
const farms = [farm(20), farm(21)]
const lots = [20,21].map(n => ({ id: id(n+20), organization_id: organizationId, farm_id: id(n), name: `Lot ${n}`, code: `${n}`, description: '', capacity: 0 }))
const animal = { id: animalId, internal_id: 'A', official_tag: null, electronic_tag: null, name: null, species_id: id(50), breed_id: id(51), gender_id: id(52), status_id: statusId, species: 'Bovino', breed: 'Raza', gender: 'Hembra', status: 'ACTIVE', farm_id: farms[0].id, lot_id: lots[0].id, farm: farms[0].name, lot: lots[0].name, birth_date: null, birth_weight: null, mother_id: null, father_id: null, notes: null, is_active: true }
const payload = { animal_id: animalId, movement_type_id: types[0].id, origin_farm_id: farms[0].id, origin_lot_id: lots[0].id, destination_farm_id: farms[1].id, destination_lot_id: lots[1].id, date: '2026-01-01', reason: 'test', notes: '' }
const record = { ...payload, id: id(60), origin_status_id: statusId }
const refreshed = { ...animal, farm_id: farms[1].id, lot_id: lots[1].id, farm: farms[1].name, lot: lots[1].name }
const validation = load('./validation.ts', {})
const updateValidation = load('./update-validation.ts', { './validation': validation })
function env(sharedProtocol) {
  let revision = 1, loggedIn = true
  const calls = [], queues = new Map(), updates = []
  const session = { getSessionRevision: () => revision, getSession: () => loggedIn ? { access: 'token' } : null, invalidateSession() { revision++ }, subscribeSession: () => () => {} }
  const api = load('../lib/api.ts', { '../auth/session': session }, { fetch: async (path, options) => {
    calls.push({ path, ...options })
    assert.ok(options.signal instanceof AbortSignal)
    assert.equal(options.headers.get('Authorization'), 'Bearer token')
    const key = ['POST','PUT','DELETE'].includes(options.method) ? options.method : path
    const queue = queues.get(key)
    assert.ok(queue?.length, `Missing response ${key}`)
    const value = await queue.shift()()
    if (value instanceof Error) throw value
    return { status: value.status ?? 200, ok: (value.status ?? 200) >= 200 && (value.status ?? 200) < 300, json: async () => value.data }
  } })
  const errors = load('../lib/api-errors.ts', { './api': api })
  const service = load('./animal-movements.service.ts', { '../lib/api': api, './validation': validation })
  const protocol = sharedProtocol ?? load('./create-protocol.ts', {})
  const h = harness()
  const Form = () => null, History = () => null, Detail = () => null, Editor = () => null, Delete = () => null
  let context = { status: 'loaded', currentOrganization: { id: organizationId }, canWrite: true }
  const component = load('./components/AnimalMovements.tsx', {
    react: h.react, 'react/jsx-runtime': jsx, '../../auth/current-context': { useCurrentContext: () => context }, '../../auth/session': session,
    '../../lib/api': api, '../../lib/api-errors': errors, '../animal-movements.service': service, '../create-protocol': protocol, '../validation': validation, '../update-validation': updateValidation, './AnimalMovementDeleteConfirmation': mod(Delete), './AnimalMovementDetail': mod(Detail), './AnimalMovementEditForm': mod(Editor),
    './AnimalMovementForm': mod(Form), './AnimalMovementHistory': mod(History),
  })
  const props = { animalId, animal, revision: 1, organizationId, canWrite: true, onAnimalUpdated: v => updates.push(v) }
  let tree
  function render(extra = {}) { Object.assign(props, extra); tree = h.render(component.MovementScope, props); return tree }
  function queue(key, ...responses) { queues.set(key, [...(queues.get(key) ?? []), ...responses.map(v => typeof v === 'function' ? v : () => v)]) }
  function defaults(history = []) {
    queue(`/api/animal-movements/animal/${props.animalId}/history`, { data: history })
    queue('/api/catalogs/movement-types', { data: types }); queue('/api/farms/', { data: farms }); queue('/api/lots/', { data: lots })
  }
  async function ready(extra, history = []) { if(extra) Object.assign(props,extra); defaults(history); render(); await tick(); render() }
  function sync(history = [record], fresh = refreshed) { queue(`/api/animal-movements/animal/${props.animalId}/history`, { data: history }); queue(`/api/animals/${props.animalId}`, { data: fresh }) }
  return { h, api, errors, service, protocol, calls, updates, props, Form, History, Detail, Editor, Delete, component, session, queue, defaults, ready, render, sync,
    form: () => find(tree, Form), history: () => find(tree, History), editor: () => find(tree, Editor), deletion: () => find(tree, Delete), detail: () => find(tree, Detail), tree: () => tree,
    changeSession: (logout = false) => { revision++; loggedIn = !logout }, context: v => { context = v },
    count: method => calls.filter(c => method === 'GET' ? !c.method : c.method === method).length,
  }
}
export { id, animalId, organizationId, statusId, types, farms, lots, animal, payload, record, refreshed, validation, updateValidation, env }
