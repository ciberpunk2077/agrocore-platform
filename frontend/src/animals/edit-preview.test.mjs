import assert from 'node:assert/strict'
import test from 'node:test'
import * as jsx from 'react/jsx-runtime'
import { Children, isValidElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { readFileSync, mkdirSync, writeFileSync } from 'node:fs'
import { load, harness, nodes, tick, deferred, mod } from '../breeding/test-support.mjs'

const id = '11111111-1111-1111-1111-111111111111', other = '22222222-2222-2222-2222-222222222222'
const validation = load('../breeding/validation.ts', {})
const helpers = load('../animals/animal-detail.ts', { '../breeding/validation': validation })
const previewFields = load('../animals/components/form/AnimalPreviewFields.tsx', { react: { Children, isValidElement }, 'react/jsx-runtime': jsx })
const animal = { id, name: 'Luna', internal_id: 'A-01', official_tag: 'OF-1', electronic_tag: 'EL-1',
  species_id: id, species: 'Bovino', breed_id: id, breed: 'Holstein', gender_id: id, gender: 'Hembra', status_id: id, status: 'Activo',
  farm_id: id, farm: 'Finca real', lot_id: other, lot: 'Lote real', birth_date: '2024-01-01', birth_weight: '30.00',
  mother_id: other, father_id: null, notes: 'Notas actuales', is_active: true }

function formSetup({ demo = true, readOnly = true, record = animal } = {}) {
  const hooks = harness(), calls = [], navigated = []
  const options = {}
  for (const name of ['getSpecies', 'getBreeds', 'getGenders', 'getAnimalStatuses', 'getFarms', 'getLots']) {
    options[name] = async () => { calls.push(name); return name === 'getLots' ? [{ id: other, farm_id: id, name: 'Lote real' }] : [{ id, species_id: id, name: 'Opción existente' }] }
  }
  const Form = load('../animals/components/form/AnimalForm.tsx', {
    react: hooks.react, 'react/jsx-runtime': jsx,
    'react-router-dom': { useNavigate: () => path => navigated.push(path) },
    '../../../components/FieldError': mod(() => null),
    '../../../lib/api-errors': { fieldErrorAttributes: () => ({}), normalizeApiError: () => ({ message: 'Error', fieldErrors: {} }) },
    '../../../auth/session': { getSession: () => ({ access: 'fake-only' }) },
    './AnimalPreviewFields': mod(previewFields.default),
    '../../animal-detail': helpers, '../../animal-options.service': options,
    '../../animals.service': {
      getParentCandidates: async () => { calls.push('getParentCandidates'); return [] },
      updateAnimal: async (...args) => { calls.push(['PUT', ...args]); return record },
      createAnimal: async (...args) => { calls.push(['POST', ...args]); return record },
    },
  }, { __AGROCORE_DEMO__: demo }).default
  const props = { animal: record, readOnly, organizationName: 'Rancho de prueba' }
  return { calls, navigated, render: () => hooks.render(Form, props) }
}

test('real preview form preloads all 15 supported fields, uses disabled fieldset and performs no option requests', async () => {
  const form = formSetup(); form.render(); await tick()
  const tree = form.render(), all = nodes(tree)
  assert.equal(all.find(n => n.type === 'fieldset').props.disabled, true)
  const expected = { internalId: 'A-01', name: 'Luna', officialTag: 'OF-1', electronicTag: 'EL-1', species: id, breed: id, gender: id,
    status: id, farm: id, lot: other, birthDate: '2024-01-01', birthWeight: '30.00', mother: other, father: '', notes: 'Notas actuales' }
  const controls = all.filter(n => ['input', 'select', 'textarea'].includes(n.type))
  assert.equal(controls.length, 15)
  for (const [key, value] of Object.entries(expected)) assert.equal(controls.find(n => n.props.id === key).props.value, value, key)
  const html = renderToStaticMarkup(tree)
  for (const label of ['Bovino', 'Holstein', 'Finca real', 'Lote real', 'Notas actuales']) assert.ok(html.includes(label))
  assert.doesNotMatch(html, /type="submit"|Guardar cambios|Eliminar/)
  assert.equal((html.match(/<(?:input|select|textarea)\b/g) ?? []).length, 15)
  for (const title of ['Identificación', 'Características biológicas', 'Clasificación', 'Ubicación y relaciones', 'Observaciones']) assert.ok(html.includes(`aria-label="${title}"`))
  assert.match(html, /Sin fotografía/); assert.doesNotMatch(html, /Fecha de creación|Creado por|Propósito|Señales particulares/)
  assert.equal(form.calls.length, 0)
  // Optional local browser fixture: actual components, synthetic test values, no API/session.
  if (process.env.AGROCORE_PREVIEW_CAPTURE === '1') {
    const page = previewSetup(async () => animal, { formContent: tree })
    page.render(); await tick()
    const css = readFileSync(new URL('../pages/AnimalEditPreviewPage.css', import.meta.url), 'utf8').replace(/^\uFEFF/, '')
    mkdirSync('preview-artifacts', { recursive: true })
    writeFileSync('preview-artifacts/animal-edit-preview.html', `<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AgroCore · Prueba visual ficticia</title><style>*{box-sizing:border-box}body{margin:0;padding:10px;background:#334155;font-family:Arial, sans-serif}button,input,select,textarea{font:inherit}${css}</style>${renderToStaticMarkup(page.render())}</html>`)
  }
})

test('programmatic preview submit cannot write in either DEMO or normal mode', async () => {
  for (const demo of [false, true]) {
    const form = formSetup({ demo }); form.render(); await tick()
    await nodes(form.render()).find(n => n.type === 'form').props.onSubmit({ preventDefault() {} })
    assert.equal(form.calls.length, 0)
    assert.equal(form.navigated.length, 0)
  }
})

test('normal editing retains catalog loading, validation, update payload and return navigation', async () => {
  const form = formSetup({ demo: false, readOnly: false }); form.render(); await tick()
  const tree = form.render()
  assert.equal(nodes(tree).find(n => n.type === 'fieldset').props.disabled, false)
  assert.ok(nodes(tree).some(n => n.props?.type === 'submit'))
  await nodes(tree).find(n => n.type === 'form').props.onSubmit({ preventDefault() {} })
  const writes = form.calls.filter(c => Array.isArray(c))
  assert.equal(writes.length, 1); assert.equal(writes[0][0], 'PUT'); assert.equal(writes[0][1], id)
  assert.equal(writes[0][2].farm_id, id); assert.equal(writes[0][2].lot_id, other)
  assert.equal(form.navigated[0], `/animals/${id}`)
  nodes(form.render()).find(n => n.props?.id === 'lot').props.onChange({ target: { value: '' } })
  await nodes(form.render()).find(n => n.type === 'form').props.onSubmit({ preventDefault() {} })
  assert.equal(form.calls.filter(c => Array.isArray(c)).length, 1)
})

function previewSetup(read, { canRead = true, session = { access: 'fake' }, formContent } = {}) {
  const hooks = harness(), scope = { revision: 1, org: id }, calls = []
  const Page = load('../pages/AnimalEditPreviewPage.tsx', {
    react: hooks.react, 'react/jsx-runtime': jsx,
    'react-router-dom': { useParams: () => ({ animalId: id }), Link: ({ to, children, ...props }) => jsx.jsx('a', { href: to, ...props, children }) },
    '../auth/current-context': { useCurrentContext: () => ({ status: 'loaded', canRead, currentOrganization: { id: scope.org, name: 'Rancho de prueba' }, isCurrentOrganization: org => org === scope.org }) },
    '../auth/useSession': { useSession: () => ({ session, revision: scope.revision }) },
    '../auth/session': { getSessionRevision: () => scope.revision },
    '../animals/animals.service': { getAnimal: async (...args) => { calls.push(args); return read() } },
    '../breeding/validation': validation,
    '../animals/components/form/AnimalPreviewFields': previewFields,
    '../animals/components/form/AnimalForm': mod(({ animal, readOnly }) => formContent ?? jsx.jsx('div', { 'data-readonly': readOnly, children: animal.name })),
  }).default
  const root = Page()
  return { scope, root, Page, calls, render: () => hooks.render(root.type, root.props) }
}

test('preview route loads selected animal, passes readonly prop and links back to same ficha', async () => {
  const page = previewSetup(async () => animal); page.render(); await tick()
  const html = renderToStaticMarkup(page.render())
  assert.match(html, /Vista previa · Solo lectura/); assert.match(html, /data-readonly="true"/); assert.match(html, /Luna/)
  assert.ok(html.includes(`href="/animals/${id}"`)); assert.equal(page.calls[0][0], id)
  assert.match(html, /Editar animal/)
  assert.match(html, /<button type="button" disabled="">Guardar cambios<\/button>/)
})

test('cross-organization denial, wrong animal and stale scope never display preview data', async () => {
  for (const read of [async () => { throw new Error('403') }, async () => ({ ...animal, id: other, name: 'FOREIGN' })]) {
    const page = previewSetup(read); page.render(); await tick()
    const html = renderToStaticMarkup(page.render())
    assert.match(html, /role="alert"/); assert.doesNotMatch(html, /FOREIGN|Luna|data-readonly/)
  }
  for (const key of ['org', 'revision']) {
    const pending = deferred(), page = previewSetup(() => pending.promise)
    page.render(); page.scope[key] = key === 'org' ? other : 2
    pending.resolve(animal); await tick()
    assert.doesNotMatch(renderToStaticMarkup(page.render()), /Luna|data-readonly/)
    assert.notEqual(page.root.key, page.Page().key)
  }
})

test('missing session/read permissions deny preview before querying; normal edit guard stays intact', () => {
  for (const auth of [{ canRead: false }, { session: null }]) {
    const page = previewSetup(async () => animal, auth)
    assert.match(renderToStaticMarkup(page.root), /role="alert"/); assert.equal(page.calls.length, 0)
  }
  const routes = readFileSync(new URL('../app/router.tsx', import.meta.url), 'utf8')
  assert.ok(routes.includes("path: '/animals/:animalId/edit-preview'"))
  assert.ok(routes.includes('<RequireWrite redirectTo="/animals/:animalId"><EditAnimalPage /></RequireWrite>'))
  const css = readFileSync(new URL('../pages/AnimalEditPreviewPage.css', import.meta.url), 'utf8')
  assert.match(css, /max-width: 600px/); assert.match(css, /focus-visible/)
  assert.match(css, /73fr/); assert.match(css, /27fr/); assert.match(css, /max-width: 800px/)
})
