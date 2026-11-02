import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import * as jsx from 'react/jsx-runtime'
import { renderToStaticMarkup } from 'react-dom/server'
import { load, harness, nodes, tick, deferred, mod } from '../breeding/test-support.mjs'

const validation = load('../breeding/validation.ts', {})
const helpers = load('../animals/animal-detail.ts', { '../breeding/validation': validation })
const GeneralInformation = load('../animals/components/AnimalGeneralInformation.tsx', {
  'react/jsx-runtime': jsx, '../animal-detail': helpers,
  '../../dashboard/components/DashboardIcon': mod(load('../dashboard/components/DashboardIcon.tsx', { 'react/jsx-runtime': jsx }).default),
}).default
const id = '11111111-1111-1111-1111-111111111111', other = '22222222-2222-2222-2222-222222222222'
const animal = { id, name: null, internal_id: 'A-001', official_tag: null, electronic_tag: null,
  species_id: id, species: 'Bovino', breed_id: id, breed: 'Holstein', gender_id: id, gender: 'Hembra', status_id: id, status: 'Activo',
  farm_id: null, farm: null, lot_id: null, lot: null, birth_date: null, birth_weight: null, mother_id: null, father_id: null, notes: null, is_active: true }

function pageSetup({ section, read = async () => animal } = {}) {
  const hooks = harness()
  const scope = { org: 'org-a', revision: 1 }
  const empty = () => null
  const imports = {
    react: hooks.react, 'react/jsx-runtime': jsx,
    'react-router-dom': { Link: ({ to, children, ...props }) => jsx.jsx('a', { href: to, ...props, children }), useParams: () => ({ animalId: id, section }) },
    '../auth/current-context': { useCurrentContext: () => ({ status: 'loaded', canRead: true, currentOrganization: { id: scope.org, name: 'Test Ranch' }, isCurrentOrganization: org => org === scope.org }) },
    '../auth/useSession': { useSession: () => ({ session: { access: 'fake-only' }, revision: scope.revision }) },
    '../auth/session': { getSessionRevision: () => scope.revision },
    '../animals/animals.service': { getAnimal: read },
    '../breeding/validation': validation,
    '../animals/animal-detail': helpers,
    '../animals/components/AnimalGeneralInformation': mod(GeneralInformation),
    '../animals/components/ExpedientBlock': mod(load('../animals/components/ExpedientBlock.tsx', {
      'react/jsx-runtime': jsx, '../../dashboard/components/DashboardIcon': mod(empty),
    }).default),
    '../animals/animal-detail.service': { getLatestAnimalWeight: async () => null },
    '../auth/WriteOnly': mod(empty),
  }
  for (const path of ['../animals/components/AnimalTimeline', '../dashboard/components/DashboardIcon', '../weights/components/WeightHistory', '../weights/components/WeightForm', '../animal-movements/components/AnimalMovements', '../vaccinations/components/Vaccinations', '../breeding/components/Breeding', '../pregnancy/components/Pregnancy', '../births/components/Births', '../production/components/ProductionHistory']) imports[path] = mod(empty)
  const Page = load('../pages/AnimalDetailPage.tsx', imports).default
  const root = Page()
  return { root, scope, Page, hooks, render: () => hooks.render(root.type, root.props) }
}

test('seven cards keep animal ID with general information first and links between every section', async () => {
  const page = pageSetup(); page.render(); await tick()
  const tree = page.render()
  const links = nodes(tree).filter(n => n.props?.className === 'animal-detail__nav-card')
  assert.equal(links.length, 7)
  assert.equal(helpers.animalSections[0].label, 'Información general')
  assert.equal(links[0].props.to, `/animals/${id}`)
  for (let i = 0; i < links.length; i++) assert.equal(links[i].props.to, helpers.animalSectionPath(id, helpers.animalSections[i].slug))
  for (const section of helpers.animalSections) {
    const view = pageSetup({ section: section.slug || undefined }); view.render(); await tick()
    const rendered = nodes(view.render())
    const cards = rendered.filter(n => n.props?.className === 'animal-detail__nav-card')
    assert.equal(cards.length, 7)
    assert.equal(cards[0].props.to, `/animals/${id}`)
    assert.equal(cards.filter(n => n.props['aria-current'] === 'page').length, 1)
    assert.equal(cards.find(n => n.props['aria-current'] === 'page').props.to, helpers.animalSectionPath(id, section.slug))
    assert.ok(rendered.some(n => n.props?.className === 'animal-detail__back' && n.props.to === '/animals'))
    if (section.slug) assert.ok(rendered.some(n => n.props?.className === 'animal-detail__back' && n.props.to === `/animals/${id}`))
    assert.equal(rendered.filter(n => n.props?.id === 'animal-general-heading').length, section.slug ? 0 : 1)
  }
})

test('general information uses real values and explicit empty states; no hidden modules mounted', async () => {
  const page = pageSetup(); page.render(); await tick(); page.render(); await tick()
  const html = renderToStaticMarkup(page.render())
  assert.match(html, /A-001/); assert.match(html, /Test Ranch/); assert.match(html, /Sin datos/)
  assert.match(html, /Vista previa de edición/)
  assert.ok(html.includes(`href="/animals/${id}/edit-preview"`))
  assert.doesNotMatch(html, /Editar animal|animal-detail__module/)
})

test('premium general information preserves every previous field and all supplied values once', () => {
  const complete = { ...animal, name: 'Luna', internal_id: 'ID-001', official_tag: 'OFF-002', electronic_tag: 'ELEC-003',
    farm: 'Finca de prueba', lot: 'Lote de prueba', birth_date: '2024-10-18', birth_weight: '32.00',
    mother_id: other, father_id: id, notes: 'Nota de prueba\nSegunda línea' }
  const html = renderToStaticMarkup(GeneralInformation({ animal: complete, businessToday: '2026-10-18', weight: '300.00 kg · 2026-10-01', weightStatus: 'loaded' }))
  const previousFields = ['Nombre', 'Sexo', 'Raza', 'Nacimiento', 'Edad', 'Último peso', 'Finca', 'Lote', 'ID interno', 'Arete oficial', 'Arete electrónico', 'Peso al nacer', 'Madre', 'Padre', 'Notas']
  for (const label of [...previousFields, 'Especie', 'Estado']) assert.equal(html.split(`<dt>${label}</dt>`).length - 1, 1, label)
  for (const value of ['Luna', 'ID-001', 'OFF-002', 'ELEC-003', 'Finca de prueba', 'Lote de prueba', '2024-10-18', '2 años', '32.00 kg', '300.00 kg', other, id, 'Segunda línea']) assert.ok(html.includes(value), value)
  for (const title of ['Identificación', 'Datos biológicos', 'Ubicación', 'Filiación', 'Observaciones']) assert.ok(html.includes(`aria-label="${title}"`))
  assert.doesNotMatch(html, /<input|<form|<button|<img/)
  assert.match(html, /Representación ilustrativa/)
  assert.match(html, /aria-hidden="true"/)
})

test('premium cards handle absent values, zero weight, loading and plain text safely', () => {
  const missing = { ...animal, internal_id: null, species: '', breed: '', gender: '', status: '', notes: '<script>not executable</script>' }
  const empty = renderToStaticMarkup(GeneralInformation({ animal: missing, businessToday: null, weight: null, weightStatus: 'error' }))
  assert.equal((empty.match(/Sin datos/g) ?? []).length, 16)
  assert.match(empty, /&lt;script&gt;/); assert.doesNotMatch(empty, /<script>/)
  const loading = renderToStaticMarkup(GeneralInformation({ animal, businessToday: null, weight: null, weightStatus: 'loading' }))
  assert.match(loading, /Cargando/)
  const zero = renderToStaticMarkup(GeneralInformation({ animal: { ...animal, birth_weight: '0.00' }, businessToday: null, weight: '0.00 kg', weightStatus: 'loaded' }))
  assert.equal((zero.match(/0\.00 kg/g) ?? []).length, 2)
})

test('premium overview responsive rules are scoped and support tablet/mobile, long text and contrast', () => {
  const css = readFileSync(new URL('./components/AnimalGeneralInformation.css', import.meta.url), 'utf8')
  for (const breakpoint of [1100, 760, 440]) assert.ok(css.includes(`max-width: ${breakpoint}px`))
  assert.match(css, /overflow-wrap: anywhere/); assert.match(css, /white-space: pre-wrap/)
  assert.match(css, /grid-template-columns: minmax\(0, 1fr\)/)
  assert.doesNotMatch(css, /\.animal-detail__header|\.animal-detail__nav|\.login|\.dashboard/)
})

test('response for another animal is rejected before displaying fields or module navigation', async () => {
  const page = pageSetup({ read: async () => ({ ...animal, id: other, name: 'FOREIGN' }) })
  page.render(); await tick()
  const html = renderToStaticMarkup(page.render())
  assert.match(html, /role="alert"/); assert.doesNotMatch(html, /FOREIGN|animal-detail__nav-card/)
})

test('late responses after organization or session change cannot populate the page; scope key changes', async () => {
  for (const key of ['org', 'revision']) {
    const pending = deferred(), page = pageSetup({ read: () => pending.promise })
    page.render(); page.scope[key] = key === 'org' ? 'org-b' : 2
    pending.resolve(animal); await tick()
    assert.doesNotMatch(renderToStaticMarkup(page.render()), /A-001/)
    assert.notEqual(page.root.key, page.Page().key)
  }
})

test('age only uses valid civil business dates, including empty/future/leap cases', () => {
  assert.equal(helpers.animalAge(null, '2026-10-18'), 'Sin datos')
  assert.equal(helpers.animalAge('2024-01-01', null), 'Sin datos')
  assert.equal(helpers.animalAge('2026-10-19', '2026-10-18'), 'Sin datos')
  assert.equal(helpers.animalAge('2026-02-30', '2026-10-18'), 'Sin datos')
  assert.equal(helpers.animalAge('2026-10-17', '2026-10-18'), '1 día')
  assert.equal(helpers.animalAge('2024-10-18', '2026-10-18'), '2 años')
  assert.equal(helpers.animalAge('2024-02-29', '2024-03-01'), '1 día')
  assert.equal(helpers.animalParentLabel(null), 'Sin datos')
  assert.match(helpers.animalParentLabel(id, { id, name: null, internal_id: 'M-1', is_deleted: true, is_active: false }), /Referencia histórica/)
})

test('timeline empty/error states are explicit; unmounted or outdated scopes ignore late data', async () => {
  for (const kind of ['empty', 'error', 'unmount', 'organization']) {
    const hooks = harness(), pending = deferred()
    let valid = true
    const current = () => valid
    const Timeline = load('../animals/components/AnimalTimeline.tsx', {
      react: hooks.react, 'react/jsx-runtime': jsx,
      '../animal-detail.service': { getAnimalTimeline: () => kind === 'error' ? Promise.reject(new Error('test-only')) : pending.promise },
    }).default
    const props = { animalId: id, accessToken: 'fake', current }
    hooks.render(Timeline, props)
    if (kind === 'unmount') hooks.unmount()
    if (kind === 'organization') valid = false
    if (kind !== 'error') pending.resolve(kind === 'empty' ? [] : [{ id, date: '2026-01-01', event_type: 'weight', title: 'LATE', description: 'LATE' }])
    await tick()
    const html = renderToStaticMarkup(hooks.render(Timeline, props))
    if (kind === 'empty') assert.match(html, /Sin datos/)
    else if (kind === 'error') assert.match(html, /role="alert"/)
    else assert.doesNotMatch(html, /LATE/)
  }
})

test('latest weight sorts real history, confirms animal identity and rejects ambiguous dates', async () => {
  let rows = [{ id, date: '2026-01-01', weight: '100.00' }, { id: other, date: '2026-10-01', weight: '200.00' }]
  let target = id
  const service = load('../animals/animal-detail.service.ts', {
    '../lib/api': {}, '../breeding/validation': validation,
    '../weights/weights.service': { getAnimalWeightHistory: async () => rows, getWeight: async weightId => ({ ...rows.find(r => r.id === weightId), animal_id: target }) },
  })
  assert.equal(await service.getLatestAnimalWeight(id, 'fake'), '200.00 kg · 2026-10-01')
  target = other; await assert.rejects(service.getLatestAnimalWeight(id, 'fake'))
  rows = []; assert.equal(await service.getLatestAnimalWeight(id, 'fake'), null)
  rows = [{ id, date: '2026-01-01', weight: '100.00' }, { id: other, date: '2026-01-01', weight: '200.00' }]
  await assert.rejects(service.getLatestAnimalWeight(id, 'fake'))
})

test('timeline uses actual GET path and rejects malformed responses instead of inventing events', async () => {
  const paths = []; let result = []
  const service = load('../animals/animal-detail.service.ts', {
    '../lib/api': { apiRequest: async (path, options) => { paths.push([path, options]); return result } },
    '../breeding/validation': validation, '../weights/weights.service': {},
  })
  assert.equal((await service.getAnimalTimeline(id, 'fake')).length, 0)
  assert.equal(paths[0][0], `/timeline/animal/${id}`)
  assert.equal(paths[0][1].method, undefined)
  result = [{ id, date: 'bad', title: 'bad', description: '', event_type: 'weight' }]
  await assert.rejects(service.getAnimalTimeline(id, 'fake'))
})

test('responsive CSS has seven/three/two/one columns, active state, wrapping and keyboard focus', () => {
  const css = readFileSync(new URL('../pages/AnimalDetailPage.css', import.meta.url), 'utf8')
  for (const count of [7, 3, 2]) assert.ok(css.includes(`repeat(${count}, minmax(0, 1fr))`))
  assert.ok(css.includes("[aria-current='page']"))
  assert.match(css, /max-width: 380px/); assert.match(css, /focus-visible/); assert.match(css, /overflow-wrap: anywhere/)
  const router = readFileSync(new URL('../app/router.tsx', import.meta.url), 'utf8')
  assert.ok(router.includes("path: '/animals/:animalId/:section'"))
  assert.ok(router.includes("path: '/animals/:animalId/edit'"))
})
