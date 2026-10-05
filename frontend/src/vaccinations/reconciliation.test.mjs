import assert from 'node:assert/strict'
import test from 'node:test'
import * as jsx from 'react/jsx-runtime'
import { animalId, vaccinationId, record, mod, tick, deferred, load, harness, nodes, text, find, button, environment } from './test-support.mjs'

function editForm(env, callbacks = {}, initialRecord = record) {
  const h = harness()
  const component = load('./components/VaccinationEditForm.tsx', {
    react: h.react, 'react/jsx-runtime': jsx, '../../auth/session': env.session,
    '../../components/FieldError': mod(() => null), '../../lib/api': env.api, '../../lib/api-errors': env.errors,
    '../civil-date': { vaccinationToday: () => '2026-10-05' }, '../validation': env.validation,
    '../vaccinations.service': env.service, '../reconciliation': env.reconciliation,
  }).default
  let saved = 0
  const props = { record: initialRecord, animalId: initialRecord.animal_id, vaccinationId: initialRecord.id, birthDate: null, onSaved: () => { saved++; callbacks.onSaved?.() }, onCancel() {}, onRecheck() {} }
  const render = () => h.render(component, props)
  return {
    h, render, saved: () => saved,
    change(field, value) { const tree = render(); const label = nodes(tree).find((node) => node.type === 'label' && text(node).startsWith(field)); const input = nodes(tree).find((node) => node.props?.id === label.props.htmlFor); input.props.onChange({ target: { value } }) },
    submit: () => find(render(), 'form').props.onSubmit({ preventDefault() {} }),
    async reconcile() { button(render(), 'Consultar registro').props.onClick(); await tick() },
  }
}

async function uncertain(env, failure = { status: 503 }, callbacks) {
  const form = editForm(env, callbacks)
  form.change('Dosis', '2')
  env.queue(failure)
  await form.submit()
  assert.equal(find(form.render(), 'fieldset').props.disabled, true)
  assert.match(text(form.render()), /No se pudo confirmar/)
  return form
}
function report(t, env, expected) { assert.deepEqual(env.counts(), expected); t.diagnostic(JSON.stringify(env.counts())) }

test('A: failed PUT, old state GET, explicit safe retry only after reconciliation', async (t) => {
  const env = environment(); const form = await uncertain(env)
  await form.submit(); assert.equal(env.counts().PUT, 1)
  env.queue({ status: 200, data: record }); await form.reconcile()
  assert.equal(form.saved(), 0)
  assert.equal(find(form.render(), 'fieldset').props.disabled, false)
  assert.match(text(form.render()), /no coincide/)
  assert.equal(env.counts().PUT, 1)
  form.change('Dosis', '2'); env.queue({ status: 200, data: { ...record, dose: '2' } }); await form.submit()
  assert.equal(form.saved(), 1)
  report(t, env, { PUT: 2, GET: 1 }); form.h.unmount()
})

for (const [label, failure, dose] of [
  ['B/503', { status: 503 }, '2'], ['B/network', new TypeError('network'), '2'],
  ['B/unexpected HTTP', { status: 202, data: record }, '2'],
  ['B/unexpected body', { status: 200, data: null }, '2'],
  ['C/equivalent decimal', { status: 503 }, '2.00'],
]) {
  test(`${label}: persisted complete payload reconciles without another PUT`, async (t) => {
    const env = environment(); const form = await uncertain(env, failure)
    const sent = JSON.parse(env.calls[0].body)
    assert.equal(sent.vaccine_name, ' Vacuna histórica ')
    env.queue({ status: 200, data: { ...record, ...sent, dose, veterinarian: '', notes: '' } })
    await form.reconcile()
    assert.equal(form.saved(), 1)
    await form.submit(); assert.equal(form.saved(), 1)
    report(t, env, { PUT: 1, GET: 1 }); form.h.unmount()
  })
}

for (const [field, value] of Object.entries({ animal_id: vaccinationId, vaccine_name: 'Different', application_date: '2026-01-02', next_application_date: '2026-01-03', dose: '3', batch: 'Different', veterinarian: 'Different', notes: 'Different' })) {
  test(`D: difference in ${field} never reconciles as success`, async (t) => {
    const env = environment(); const form = await uncertain(env)
    env.queue({ status: 200, data: { ...record, dose: '2', [field]: value } }); await form.reconcile()
    assert.equal(form.saved(), 0)
    assert.equal(find(form.render(), 'fieldset').props.disabled, field === 'animal_id')
    report(t, env, { PUT: 1, GET: 1 }); form.h.unmount()
  })
}

test('Decimal and optional text semantics reject invalid values and preserve whitespace', () => {
  const env = environment(); const snapshot = env.reconciliation.vaccinationSnapshot({ ...record, dose: '02.00' })
  assert.ok(Object.isFrozen(snapshot)); assert.equal(snapshot.dose, '2')
  assert.equal(snapshot.veterinarian, ''); assert.equal(snapshot.batch, ' Lote ')
  for (const dose of ['2', '2.0', '2.00', '002.00']) assert.ok(env.reconciliation.matchesVaccinationSnapshot({ ...record, dose }, vaccinationId, snapshot))
  for (const dose of ['2x', '2e0', ' 2', '2.000', 'NaN', '0', '-2', '1000000']) assert.equal(env.reconciliation.matchesVaccinationSnapshot({ ...record, dose }, vaccinationId, snapshot), false)
  assert.equal(env.reconciliation.matchesVaccinationSnapshot({ ...record, dose: '2', batch: 'Lote' }, vaccinationId, snapshot), false)
  assert.equal(env.reconciliation.matchesVaccinationSnapshot({ ...record, dose: '2', next_application_date: '' }, vaccinationId, snapshot), false)
  assert.deepEqual(Object.keys(snapshot).sort(), ['animal_id', 'vaccine_name', 'application_date', 'next_application_date', 'dose', 'batch', 'veterinarian', 'notes'].sort())
})

function container(env) {
  const h = harness(); const Form = () => null; const Preparation = () => null; const History = () => null
  const component = load('./components/Vaccinations.tsx', {
    '../../auth/current-context': { useCurrentContext: () => ({ currentOrganization: { id: 'tenant-A' } }) },
    react: h.react, 'react/jsx-runtime': jsx, '../../auth/WriteOnly': mod(() => null),
    './VaccinationDeleteConfirmation': mod(() => null), './VaccinationForm': mod(Form), './VaccinationPreparation': mod(Preparation), './VaccinationHistory': mod(History),
  }).default
  const props = { animalId, birthDate: null }; const parent = component(props).type
  const render = () => h.render(parent, props)
  const RealHistory = (historyH) => load('./components/VaccinationHistory.tsx', {
    react: historyH.react, 'react/jsx-runtime': jsx, '../../auth/session': env.session,
    '../../auth/WriteOnly': mod(() => null), '../vaccinations.service': env.service,
  }).default
  return { h, render, Form, Preparation, History, RealHistory }
}

test('E: confirmed PUT + failed history refresh retains success; retry is GET only', async (t) => {
  const env = environment(); const parent = container(env)
  find(parent.render(), parent.History).props.onEdit(vaccinationId)
  const callbacks = find(parent.render(), parent.Preparation).props
  const form = editForm(env, callbacks); form.change('Dosis', '2')
  env.queue({ status: 200, data: { ...record, dose: '2' } }); await form.submit()
  assert.match(text(parent.render()), /Vacunación actualizada correctamente/)
  const historyH = harness(); const History = parent.RealHistory(historyH)
  let props = find(parent.render(), parent.History).props
  env.queue({ status: 503 }); historyH.render(History, props); await tick()
  let tree = historyH.render(History, props)
  assert.match(text(tree), /fue actualizada, pero/)
  assert.match(text(parent.render()), /Vacunación actualizada correctamente/)
  env.queue({ status: 200, data: [{ ...record, dose: '2' }] })
  button(tree, 'Actualizar historial').props.onClick()
  historyH.render(History, props); await tick()
  tree = historyH.render(History, props)
  assert.ok(!text(tree).includes('no se pudo'))
  assert.match(text(parent.render()), /Vacunación actualizada correctamente/)
  await form.submit()
  report(t, env, { PUT: 1, GET: 2 }); historyH.unmount(); form.h.unmount()
})

test('B integration: reconciled success refreshes history and releases parent write lock', async (t) => {
  const env = environment(); const parent = container(env)
  find(parent.render(), parent.History).props.onEdit(vaccinationId)
  const form = await uncertain(env, { status: 503 }, find(parent.render(), parent.Preparation).props)
  assert.equal(find(parent.render(), parent.Form), undefined)
  assert.equal(find(parent.render(), parent.History).props.actionsDisabled, true)
  env.queue({ status: 200, data: { ...record, dose: '2.00' } }); await form.reconcile()
  assert.match(text(parent.render()), /Vacunación actualizada correctamente/)
  assert.ok(find(parent.render(), parent.Form))
  const props = find(parent.render(), parent.History).props
  assert.equal(props.saved, 'updated'); assert.equal(props.actionsDisabled, false)
  const historyH = harness(); const History = parent.RealHistory(historyH)
  env.queue({ status: 200, data: [{ ...record, dose: '2.00' }] })
  historyH.render(History, props); await tick()
  report(t, env, { PUT: 1, GET: 2 }); form.h.unmount(); historyH.unmount()
})

test('F: double submit and double reconciliation action produce one PUT and one GET', async (t) => {
  const env = environment(); const wait = deferred(); const form = editForm(env)
  form.change('Dosis', '2'); env.queue(() => wait.promise)
  const first = form.submit(); await form.submit(); wait.resolve({ status: 503 }); await first
  await form.submit(); await form.submit()
  const read = deferred(); env.queue(() => read.promise)
  const action = button(form.render(), 'Consultar registro').props.onClick
  action(); action(); await form.submit()
  assert.equal(button(form.render(), 'Consultar registro').props.disabled, true)
  read.resolve({ status: 200, data: { ...record, dose: '2' } }); await tick()
  assert.equal(form.saved(), 1); report(t, env, { PUT: 1, GET: 1 }); form.h.unmount()
})

test('Failed reconciliation keeps uncertainty and only permits another GET', async (t) => {
  const env = environment(); const form = await uncertain(env)
  env.queue({ status: 503 }); await form.reconcile(); await form.submit()
  assert.equal(find(form.render(), 'fieldset').props.disabled, true)
  env.queue({ status: 200, data: { ...record, dose: '2' } }); await form.reconcile()
  assert.equal(form.saved(), 1); report(t, env, { PUT: 1, GET: 2 }); form.h.unmount()
})

for (const change of ['session', 'abort/A-B-A']) {
  test(`G: ${change} during reconciliation ignores late success`, async (t) => {
    const env = environment(); const form = await uncertain(env)
    const read = deferred(); env.queue(() => read.promise)
    button(form.render(), 'Consultar registro').props.onClick()
    const signal = env.calls.at(-1).signal
    let newForm
    if (change === 'session') env.changeSession()
    else {
      form.h.unmount(); assert.equal(signal.aborted, true)
      const b = editForm(env, {}, { ...record, id: animalId, animal_id: vaccinationId }); b.render(); b.h.unmount()
      newForm = editForm(env); newForm.render()
    }
    read.resolve({ status: 200, data: { ...record, dose: '2' } }); await tick()
    assert.equal(form.saved(), 0)
    if (newForm) { assert.equal(newForm.saved(), 0); assert.equal(find(newForm.render(), 'fieldset').props.disabled, false); newForm.h.unmount() }
    else { await form.reconcile(); assert.equal(env.calls.length, 2) }
    report(t, env, { PUT: 1, GET: 1 }); form.h.unmount()
  })
}

for (const wrong of [{ id: animalId }, { animal_id: vaccinationId }, { is_active: false }]) {
  test(`H: invalid GET identity/active ${JSON.stringify(wrong)} retains uncertainty`, async (t) => {
    const env = environment(); const form = await uncertain(env)
    env.queue({ status: 200, data: { ...record, dose: '2', ...wrong } }); await form.reconcile()
    assert.equal(form.saved(), 0); assert.equal(find(form.render(), 'fieldset').props.disabled, true)
    await form.submit(); report(t, env, { PUT: 1, GET: 1 }); form.h.unmount()
  })
}
