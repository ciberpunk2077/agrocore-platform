import assert from 'node:assert/strict'
import test from 'node:test'
import * as jsx from 'react/jsx-runtime'
import { animalId, vaccinationId, record, mod, tick, deferred, load, harness, nodes, text, find, button, environment } from './test-support.mjs'

const counts = (env) => ({ DELETE: env.calls.filter((call) => call.method === 'DELETE').length, GET: env.calls.filter((call) => !call.method).length })
function report(t, env, expected) { assert.deepEqual(counts(env), expected); t.diagnostic(JSON.stringify(counts(env))) }
function context(env) { return { useCurrentContext: () => env.context ?? { canWrite: true, currentOrganization: { id: 'tenant-A' } } } }

function confirmation(env, callbacks = {}, ids = {}) {
  const h = harness(); let deleted = 0; let unavailable = 0; let cancelled = 0
  const props = { animalId, vaccinationId, ...ids, onDeleted: () => { deleted++; callbacks.onDeleted?.() }, onUnavailable: () => { unavailable++; callbacks.onUnavailable?.() }, onCancel: () => { cancelled++; callbacks.onCancel?.() } }
  const Wrapper = load('./components/VaccinationDeleteConfirmation.tsx', {
    react: h.react, 'react/jsx-runtime': jsx, '../../auth/current-context': context(env), '../../auth/session': env.session,
    '../../lib/api': env.api, '../../lib/api-errors': env.errors, '../vaccinations.service': env.service,
  }).default
  const element = Wrapper(props)
  const render = () => element ? h.render(element.type, props) : null
  return { h, render, element, Wrapper, props, deleted: () => deleted, unavailable: () => unavailable, cancelled: () => cancelled,
    confirm: () => button(render(), 'Confirmar eliminación')?.props.onClick(),
    reconcile: () => button(render(), 'Consultar registro')?.props.onClick() }
}
async function ready(env, callbacks) {
  env.queue({ status: 200, data: record })
  const form = confirmation(env, callbacks); form.render(); await tick()
  assert.ok(button(form.render(), 'Confirmar eliminación'))
  return form
}
async function uncertain(env, failure = { status: 503 }, callbacks) {
  const form = await ready(env, callbacks)
  env.queue(failure); form.confirm(); await tick()
  assert.equal(button(form.render(), 'Confirmar eliminación'), undefined)
  assert.equal(button(form.render(), 'Cancelar'), undefined)
  assert.ok(button(form.render(), 'Consultar registro'))
  assert.equal(form.deleted(), 0)
  return form
}

test('Preparation identifies vaccine/date/dose/id; cancellation makes zero DELETE', async (t) => {
  const env = environment(); const form = await ready(env)
  for (const value of [record.vaccine_name, '01/01/2026', record.dose, vaccinationId]) assert.ok(text(form.render()).includes(value))
  button(form.render(), 'Cancelar').props.onClick(); assert.equal(form.cancelled(), 1)
  report(t, env, { DELETE: 0, GET: 1 }); form.h.unmount()
})

test('Double confirmation sends exactly one bodyless DELETE; pending blocks cancellation', async (t) => {
  const env = environment(); const form = await ready(env); const wait = deferred()
  const cancel = button(form.render(), 'Cancelar').props.onClick
  const action = button(form.render(), 'Confirmar eliminación').props.onClick
  env.queue(() => wait.promise); action(); action(); cancel()
  assert.equal(form.cancelled(), 0)
  assert.equal(button(form.render(), 'Cancelar').props.disabled, true)
  assert.equal(button(form.render(), 'Confirmar eliminación').props.disabled, true)
  assert.equal(env.calls.at(-1).body, undefined)
  assert.equal(env.calls.at(-1).path, `/api/vaccinations/${vaccinationId}`)
  wait.resolve({ status: 200, data: { success: true } }); await tick(); action()
  assert.equal(form.deleted(), 1); report(t, env, { DELETE: 1, GET: 1 }); form.h.unmount()
})

for (const [label, failure] of [
  ['network', new TypeError('lost response')], ['503', { status: 503 }], ['204', { status: 204 }],
  ['empty body', { status: 200, data: null }], ['invalid JSON', { status: 200, jsonError: true }],
  ['false success', { status: 200, data: { success: false } }], ['string success', { status: 200, data: { success: 'true' } }],
]) {
  test(`${label}: uncertain DELETE reconciled by 404 means unavailable, never success`, async (t) => {
    const env = environment(); const form = await uncertain(env, failure)
    env.queue({ status: 404 }); form.reconcile(); await tick()
    assert.equal(form.deleted(), 0); assert.equal(form.unavailable(), 1)
    report(t, env, { DELETE: 1, GET: 2 }); form.h.unmount()
  })
}

test('Uncertain + valid active GET permits only a new explicit confirmation; double GET is guarded', async (t) => {
  const env = environment(); const form = await uncertain(env); const read = deferred()
  const reconcile = button(form.render(), 'Consultar registro').props.onClick
  env.queue(() => read.promise); reconcile(); reconcile(); form.confirm()
  assert.equal(button(form.render(), 'Consultar registro').props.disabled, true)
  read.resolve({ status: 200, data: record }); await tick()
  assert.match(text(form.render()), /sigue disponible/)
  assert.equal(form.deleted(), 0); assert.equal(counts(env).DELETE, 1)
  env.queue({ status: 200, data: { success: true } }); form.confirm(); await tick()
  assert.equal(form.deleted(), 1); report(t, env, { DELETE: 2, GET: 2 }); form.h.unmount()
})

for (const response of [{ status: 503 }, new TypeError('GET network'), { status: 200, data: null },
  { status: 200, data: { ...record, id: animalId } }, { status: 200, data: { ...record, animal_id: vaccinationId } },
  { status: 200, data: { ...record, is_active: false } }, { status: 403 }, { status: 401 }]) {
  test(`Failed/invalid reconciliation retains write block: ${JSON.stringify(response)}`, async (t) => {
    const env = environment(); const form = await uncertain(env)
    env.queue(response); form.reconcile(); await tick(); form.confirm()
    assert.equal(form.deleted(), 0); assert.equal(form.unavailable(), 0)
    assert.equal(button(form.render(), 'Confirmar eliminación'), undefined)
    report(t, env, { DELETE: 1, GET: 2 }); form.h.unmount()
  })
}

for (const wrong of [{ id: animalId }, { animal_id: vaccinationId }, { is_active: false }]) {
  test(`Invalid preparation never enables DELETE: ${JSON.stringify(wrong)}`, async (t) => {
    const env = environment(); env.queue({ status: 200, data: { ...record, ...wrong } })
    const form = confirmation(env); form.render(); await tick(); form.confirm()
    assert.equal(button(form.render(), 'Confirmar eliminación'), undefined)
    report(t, env, { DELETE: 0, GET: 1 }); form.h.unmount()
  })
}

test('VIEWER confirmation produces no GET or DELETE', (t) => {
  const env = environment(); env.context = { canWrite: false, currentOrganization: { id: 'tenant-A' } }
  const form = confirmation(env); assert.equal(form.render(), null)
  report(t, env, { DELETE: 0, GET: 0 })
})

for (const change of ['session', 'abort/A-B-A', 'tenant']) {
  test(`Late reconciliation cannot contaminate current view after ${change}`, async (t) => {
    const env = environment(); const form = await uncertain(env); const read = deferred()
    env.queue(() => read.promise); form.reconcile()
    if (change === 'session') env.changeSession()
    else {
      if (change === 'tenant') {
        env.context = { canWrite: true, currentOrganization: { id: 'tenant-B' } }
        assert.notEqual(form.Wrapper(form.props).key, form.element.key)
      }
      form.h.unmount(); assert.equal(env.calls.at(-1).signal.aborted, true)
      const fresh = confirmation(env, {}, change === 'abort/A-B-A' ? { animalId: vaccinationId, vaccinationId: animalId } : {})
      assert.notEqual(fresh.element.key, form.element.key)
      fresh.h.unmount()
      const back = confirmation(env); assert.equal(back.deleted(), 0); assert.equal(back.unavailable(), 0)
    }
    read.resolve({ status: 404 }); await tick()
    assert.equal(form.deleted(), 0); assert.equal(form.unavailable(), 0)
    report(t, env, { DELETE: 1, GET: 2 }); form.h.unmount()
  })
}

function container(env) {
  const h = harness(); const Form = () => null; const Preparation = () => null; const History = () => null; const Delete = () => null
  const Wrapper = load('./components/Vaccinations.tsx', {
    react: h.react, 'react/jsx-runtime': jsx, '../../auth/current-context': context(env), '../../auth/WriteOnly': mod(() => null),
    './VaccinationForm': mod(Form), './VaccinationPreparation': mod(Preparation), './VaccinationHistory': mod(History), './VaccinationDeleteConfirmation': mod(Delete),
  }).default
  const props = { animalId, birthDate: null }; const element = Wrapper(props)
  const render = () => h.render(element.type, props)
  const realHistory = (historyH) => load('./components/VaccinationHistory.tsx', {
    react: historyH.react, 'react/jsx-runtime': jsx, '../../auth/session': env.session, '../vaccinations.service': env.service,
    '../../auth/WriteOnly': mod(() => null),
  }).default
  return { h, render, Wrapper, props, element, Form, Preparation, History, Delete, realHistory }
}

test('Parent gates Edit/Delete/Create draft synchronously and cancellation releases draft', () => {
  const env = environment(); const parent = container(env)
  let tree = parent.render(); const actions = find(tree, parent.History).props
  assert.equal(actions.actionsDisabled, false)
  const draft = find(tree, parent.Form).props
  assert.equal(draft.onDraftBegin(), true); actions.onDelete(vaccinationId); actions.onEdit(vaccinationId)
  tree = parent.render(); assert.equal(find(tree, parent.History).props.actionsDisabled, true)
  assert.equal(find(tree, parent.Delete), undefined); assert.equal(find(tree, parent.Preparation), undefined)
  draft.onDraftCancel(); tree = parent.render(); assert.equal(find(tree, parent.History).props.actionsDisabled, false)
  const freshActions = find(tree, parent.History).props; freshActions.onDelete(vaccinationId); freshActions.onEdit(vaccinationId); freshActions.onDelete(animalId)
  tree = parent.render(); assert.ok(find(tree, parent.Delete)); assert.equal(find(tree, parent.Preparation), undefined); assert.equal(find(tree, parent.Form), undefined)
  assert.equal(find(tree, parent.Delete).props.vaccinationId, vaccinationId)
  assert.equal(draft.onDraftBegin(), false); assert.equal(draft.onBegin(), false)
  find(tree, parent.Delete).props.onCancel()
  find(parent.render(), parent.History).props.onEdit(vaccinationId)
  tree = parent.render(); find(tree, parent.History).props.onDelete(vaccinationId)
  assert.equal(find(parent.render(), parent.Delete), undefined)
})

test('Actual CREATE input starts draft, preserves guards and cancel cleans via parent remount', () => {
  const env = environment(); const parent = container(env); const h = harness()
  const Form = load('./components/VaccinationForm.tsx', {
    react: h.react, 'react/jsx-runtime': jsx, '../../auth/session': env.session, '../../lib/api': env.api,
    '../../lib/api-errors': env.errors, '../../components/FieldError': mod(() => null), '../validation': env.validation,
    '../civil-date': { vaccinationToday: () => '2026-10-05' }, '../vaccinations.service': env.service,
  }).default
  const element = find(parent.render(), parent.Form); let tree = h.render(Form, element.props)
  assert.equal(button(tree, 'Cancelar registro'), undefined)
  nodes(tree).find((node) => node.type === 'input').props.onChange({ target: { value: 'Draft' } })
  tree = h.render(Form, element.props); assert.equal(find(parent.render(), parent.History).props.actionsDisabled, true)
  button(tree, 'Cancelar registro').props.onClick()
  const next = find(parent.render(), parent.Form); assert.notEqual(next.key, element.key)
  h.unmount(); const fresh = harness(); tree = fresh.render(Form, next.props)
  assert.equal(nodes(tree).find((node) => node.type === 'input').props.value, '')
  assert.equal(find(parent.render(), parent.History).props.actionsDisabled, false); fresh.unmount()
})

for (const status of [200, 400, 503]) {
  test(`Actual CREATE pending and response ${status} coordinate with DELETE safely`, async (t) => {
    const env = environment(); const parent = container(env); const h = harness()
    const Form = load('./components/VaccinationForm.tsx', {
      react: h.react, 'react/jsx-runtime': jsx, '../../auth/session': env.session, '../../lib/api': env.api,
      '../../lib/api-errors': env.errors, '../../components/FieldError': mod(() => null), '../validation': env.validation,
      '../civil-date': { vaccinationToday: () => '2026-10-05' }, '../vaccinations.service': env.service,
    }).default
    const props = find(parent.render(), parent.Form).props
    for (const [id, value] of [['vaccination-name', 'New'], ['vaccination-date', '2026-01-01'], ['vaccination-dose', '2']]) {
      const tree = h.render(Form, props)
      nodes(tree).find((node) => node.props?.id === id).props.onChange({ target: { value } })
    }
    const response = deferred(); env.queue(() => response.promise)
    const submit = find(h.render(Form, props), 'form').props.onSubmit
    const pending = submit({ preventDefault() {} }); await submit({ preventDefault() {} })
    find(parent.render(), parent.History).props.onDelete(vaccinationId)
    assert.equal(find(parent.render(), parent.Delete), undefined)
    button(h.render(Form, props), 'Cancelar registro').props.onClick()
    assert.equal(find(parent.render(), parent.History).props.actionsDisabled, true)
    response.resolve({ status, data: status === 200 ? { ...record, vaccine_name: 'New', dose: '2' } : { detail: 'Simulated failure' } })
    await pending
    let tree = h.render(Form, props)
    if (status === 200) {
      assert.equal(find(parent.render(), parent.History).props.actionsDisabled, false)
      assert.match(text(parent.render()), /registrada correctamente/)
    } else if (status === 400) {
      assert.equal(find(parent.render(), parent.History).props.actionsDisabled, true)
      button(tree, 'Cancelar registro').props.onClick()
      assert.equal(find(parent.render(), parent.History).props.actionsDisabled, false)
    } else {
      assert.equal(button(tree, 'Cancelar registro'), undefined)
      assert.equal(find(tree, 'fieldset').props.disabled, true)
      find(parent.render(), parent.History).props.onDelete(vaccinationId)
      assert.equal(find(parent.render(), parent.Delete), undefined)
      await find(tree, 'form').props.onSubmit({ preventDefault() {} })
    }
    assert.equal(env.calls.filter((call) => call.method === 'POST').length, 1)
    report(t, env, { DELETE: 0, GET: 0 }); h.unmount()
  })
}

for (const phase of ['preparation', 'DELETE pending']) {
  test(`Session change during ${phase} discards old result`, async (t) => {
    const env = environment(); const wait = deferred(); let form
    if (phase === 'preparation') {
      env.queue(() => wait.promise); form = confirmation(env); form.render(); await tick()
    } else {
      form = await ready(env); env.queue(() => wait.promise); form.confirm()
    }
    env.changeSession()
    wait.resolve({ status: 200, data: phase === 'preparation' ? record : { success: true } }); await tick()
    assert.equal(form.deleted(), 0); assert.equal(form.unavailable(), 0)
    form.confirm()
    report(t, env, { DELETE: phase === 'preparation' ? 0 : 1, GET: 1 }); form.h.unmount()
  })
}

for (const unavailable of [false, true]) {
  test(`Parent ${unavailable ? 'unavailable' : 'confirmed success'} survives refresh failure and retries only GET`, async (t) => {
    const env = environment(); const parent = container(env)
    find(parent.render(), parent.History).props.onView(vaccinationId)
    find(parent.render(), parent.History).props.onDelete(vaccinationId)
    const callbacks = find(parent.render(), parent.Delete).props
    const form = unavailable ? await uncertain(env, { status: 503 }, callbacks) : await ready(env, callbacks)
    if (unavailable) { env.queue({ status: 404 }); form.reconcile() }
    else { env.queue({ status: 200, data: { success: true } }); form.confirm() }
    await tick()
    let tree = parent.render(); const expected = unavailable ? 'ya no está disponible' : 'eliminada correctamente'
    assert.ok(text(tree).includes(expected)); if (unavailable) assert.ok(!text(tree).includes('eliminada correctamente'))
    assert.equal(find(tree, parent.Delete), undefined)
    assert.equal(find(tree, parent.Preparation), undefined)
    const historyH = harness(); const History = parent.realHistory(historyH); const props = find(tree, parent.History).props
    env.queue({ status: 503 }); historyH.render(History, props); await tick()
    let history = historyH.render(History, props); assert.ok(text(parent.render()).includes(expected))
    if (!unavailable) assert.match(text(history), /fue eliminada, pero/)
    env.queue({ status: 200, data: [record] }); button(history, 'Actualizar historial').props.onClick()
    historyH.render(History, props); await tick(); history = historyH.render(History, props)
    assert.equal(button(history, 'Eliminar'), undefined)
    assert.ok(text(parent.render()).includes(expected))
    report(t, env, { DELETE: 1, GET: unavailable ? 4 : 3 }); form.h.unmount(); historyH.unmount()
  })
}

test('Ver detalles/Volver cause zero DELETE; animal and tenant keys reset all selection state', (t) => {
  const env = environment(); const parent = container(env)
  find(parent.render(), parent.History).props.onView(vaccinationId)
  const detail = find(parent.render(), parent.Preparation)
  assert.equal(detail.props.readOnly, true); detail.props.onCancel()
  assert.equal(find(parent.render(), parent.Preparation), undefined)
  find(parent.render(), parent.History).props.onDelete(vaccinationId)
  assert.notEqual(parent.Wrapper({ ...parent.props, animalId: vaccinationId }).key, parent.element.key)
  env.context = { canWrite: true, currentOrganization: { id: 'tenant-B' } }
  assert.notEqual(parent.Wrapper(parent.props).key, parent.element.key)
  report(t, env, { DELETE: 0, GET: 0 })
})
