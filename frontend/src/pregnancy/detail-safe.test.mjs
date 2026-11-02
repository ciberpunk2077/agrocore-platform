import { detailImports } from '../reproduction/test-support.mjs'
import assert from 'node:assert/strict'
import test from 'node:test'
import * as jsx from 'react/jsx-runtime'
import { load, harness, deferred, tick, text, nodes, mod } from '../breeding/test-support.mjs'
import { id } from '../breeding/flow-test-support.mjs'
import { env, animal, breeding, payload, record } from './flow-test-support.mjs'
const path = r => `/api/pregnancies/${r.id}`
const other = { ...record, id: id(151), breeding_id: id(152), status: 'FINISHED' }
const state = e => e.history().props.detail

test('opening DETAIL uses individual no-store GET, signal and fresh values, no writes', async () => {
  const e = env(); await e.ready({ canWrite: false, businessTimeLease: null }, [record])
  const fresh = { ...record, notes: 'fresh', status: 'ABORTED', diagnosis_date: '2026-10-04' }
  e.queue(path(record), { data: fresh }); await e.history().props.onOpenDetail(record.id); e.render()
  assert.equal(state(e).status, 'success'); assert.equal(state(e).record.notes, 'fresh'); assert.equal(state(e).record.status, 'ABORTED')
  const call = e.calls.at(-1); assert.equal(call.path, path(record)); assert.equal(call.cache, 'no-store'); assert.ok(call.signal instanceof AbortSignal)
  assert.equal(e.count('POST'), 0); assert.ok(e.calls.every(c => !c.method))
})
for (const data of [null, {}, { ...record, id: id(999) }, { ...record, animal_id: id(999) }, { ...record, breeding_id: id(999) },
  { ...record, diagnosis_date: '2026-02-30' }, { ...record, expected_birth: 'bad' }, { ...record, confirmed: 'true' },
  { ...record, notes: 1 }, { ...record, status: 'UNKNOWN' }]) {
  test(`invalid detail never becomes success or falls back to HISTORY ${JSON.stringify(data)}`, async () => {
    const e = env(); await e.ready({ canWrite: false }, [{ ...record, notes: 'snapshot secret' }])
    e.queue(path(record), { data }); await e.history().props.onOpenDetail(record.id); e.render()
    assert.equal(state(e).status, 'error'); assert.equal(state(e).record, undefined); assert.equal(e.history().props.history.length, 1)
    e.queue(path(record), { data: record }); await e.history().props.onOpenDetail(record.id); e.render()
    assert.equal(state(e).status, 'success'); assert.equal(e.count('POST'), 0)
  })
}
for (const status of [404, 403, 500]) {
  test(`HTTP ${status} is recoverable by GET and does not destroy HISTORY`, async () => {
    const e = env(); await e.ready({ canWrite: false }, [record]); e.queue(path(record), { status, data: { detail: 'No tienes permiso' } })
    await e.history().props.onOpenDetail(record.id); e.render(); assert.equal(state(e).status, 'error')
    if (status === 404) assert.match(state(e).message, /ya no está disponible/)
    if (status === 403) { assert.match(state(e).message, /permiso/); assert.doesNotMatch(state(e).message, /ya no está disponible/) }
    assert.equal(e.history().props.history.length, 1)
    e.queue(path(record), { data: record }); await e.history().props.onOpenDetail(record.id); e.render(); assert.equal(state(e).status, 'success')
    assert.ok(e.calls.every(c => !c.method))
  })
}
test('401 uses global session invalidation and cannot publish stale detail', async () => {
  const e = env(); await e.ready({ canWrite: false }, [record]); e.queue(path(record), { status: 401 })
  await e.history().props.onOpenDetail(record.id); e.render(); assert.notEqual(state(e).status, 'success')
  e.h.unmount(); assert.equal(e.count('POST'), 0)
})
for (const success of [false, true]) {
  test(`close ${success ? 'after success' : 'while loading'} cancels and never reopens`, async () => {
    const e = env(); await e.ready({ canWrite: false }, [record]); const d = deferred()
    e.queue(path(record), success ? { data: record } : () => d.promise)
    const work = e.history().props.onOpenDetail(record.id); await tick(); e.render()
    e.history().props.onCloseDetail(); e.render(); assert.equal(state(e).status, 'idle'); assert.equal(e.calls.at(-1).signal.aborted, true)
    if (!success) d.resolve({ data: record }); await work; e.render(); assert.equal(state(e).status, 'idle')
  })
}
for (const late of [{ data: record }, { status: 404 }, new TypeError('late network')]) {
  test(`X to Y rejects late X result/error ${JSON.stringify(late)}`, async () => {
    const e = env(); await e.ready({ canWrite: false }, [record, other]); const d = deferred()
    e.queue(path(record), () => d.promise); const x = e.history().props.onOpenDetail(record.id); await tick(); e.render()
    const firstSignal = e.calls.at(-1).signal
    e.queue(path(other), { data: { ...other, notes: 'Y only' } }); await e.history().props.onOpenDetail(other.id); e.render()
    assert.equal(firstSignal.aborted, true); assert.equal(state(e).pregnancyId, other.id)
    d.resolve(late); await x; e.render(); assert.equal(state(e).record.notes, 'Y only'); assert.equal(state(e).pregnancyId, other.id)
  })
}
for (const change of ['animal', 'animal A to B to A', 'logout/login', 'organization', 'unmount']) {
  test(`scope ${change} ignores old DETAIL despite transport completing after abort`, async () => {
    const e = env(); await e.ready({ canWrite: false }, [record]); const d = deferred(); e.queue(path(record), () => d.promise)
    const work = e.history().props.onOpenDetail(record.id); await tick(); e.render()
    if (change === 'logout/login') e.changeSession()
    else if (change === 'organization') e.context({ currentOrganization: { id: id(999) } })
    e.h.unmount(); assert.equal(e.calls.at(-1).signal.aborted, true)
    const next = env(); await next.ready({ canWrite: false, animal: change === 'animal' ? { ...animal, id: id(99) } : animal }, change === 'animal' ? [] : [record])
    const before = e.h.slots.slice(); d.resolve({ data: { ...record, notes: 'old' } }); await work
    assert.deepEqual(e.h.slots.slice(), before); assert.equal(state(next).status, 'idle')
    if (change === 'animal A to B to A') {
      next.queue(path(record), { data: { ...record, notes: 'new A' } }); await next.history().props.onOpenDetail(record.id); next.render()
      assert.equal(state(next).record.notes, 'new A')
    }
  })
}
test('same-scope session or tenant change rejects late response before unmount', async () => {
  for (const change of ['session', 'tenant']) {
    const e = env(); await e.ready({ canWrite: false }, [record]); const d = deferred(); e.queue(path(record), () => d.promise)
    const work = e.history().props.onOpenDetail(record.id); await tick(); e.render()
    if (change === 'session') e.changeSession(); else e.context({ currentOrganization: { id: id(999) } })
    d.resolve({ data: record }); await work; e.render(); assert.equal(state(e).status, 'loading'); e.h.unmount()
  }
})
test('DETAIL cannot change uncertain CREATE or unblock its registry', async () => {
  const e = env(); await e.ready({}, [{ ...other, status: 'ABORTED' }]); e.prepare(); e.queue('POST', { status: 503 })
  await e.form().props.onCreate(payload); e.render(); assert.match(text(e.tree()), /Resultado incierto/)
  e.queue(path(other), { data: other }); await e.history().props.onOpenDetail(other.id); e.render()
  assert.equal(state(e).status, 'success'); assert.equal(e.form().props.disabled, true); assert.equal(e.count('POST'), 1)
  e.history().props.onCloseDetail(); await e.form().props.onCreate(payload); assert.equal(e.count('POST'), 1)
})
test('DETAIL cannot interfere with pending or confirmed CREATE', async () => {
  const e = env(); await e.ready({}, [{ ...other, status: 'ABORTED' }]); e.prepare(); const d = deferred(); e.queue('POST', () => d.promise)
  const work = e.form().props.onCreate(payload); await tick(); e.render()
  e.queue(path(other), { data: other }); await e.history().props.onOpenDetail(other.id); e.render(); assert.equal(e.form().props.disabled, true)
  e.sync([record, other]); d.resolve({ data: record }); await work; e.render(); assert.match(text(e.tree()), /guardada correctamente/); assert.equal(e.count('POST'), 1)
})
test('real HISTORY renders exactly one fresh detail, no cached notes fallback or detail write control', () => {
  const h = harness(), onOpen = [], onClose = []
  const component = load('../pregnancy/components/PregnancyHistory.tsx', { ...detailImports, 'react/jsx-runtime': jsx, '../../auth/WriteOnly': mod(() => null) })
  const base = { history: [{ ...record, notes: 'cached secret' }, other], eventLabels: new Map(), disabled: true,
    onAbort() {}, onOpenDetail: id => onOpen.push(id), onCloseDetail: () => onClose.push(true) }
  let tree = h.render(component.default, { ...base, detail: { status: 'idle' } })
  assert.doesNotMatch(text(tree), /cached secret/); assert.equal(nodes(tree).filter(n => n.type === 'button' && text(n).includes('Ver detalles')).length, 2)
  nodes(tree).find(n => n.type === 'button' && text(n).includes('Ver detalles')).props.onClick({ preventDefault() {} }); assert.equal(onOpen[0], record.id)
  tree = h.render(component.default, { ...base, detail: { status: 'success', pregnancyId: record.id, record: { ...record, notes: 'fresh notes' } } })
  assert.match(text(tree), /fresh notes/); assert.doesNotMatch(text(tree), /cached secret/)
  assert.equal(nodes(tree).filter(n => n.type === 'section' && n.props.className === 'repro-detail').length, 1)
  nodes(tree).find(n => n.type === 'button' && text(n).includes('Ver detalles')).props.onClick({ preventDefault() {} }); assert.equal(onClose.length, 1)
  tree = h.render(component.default, { ...base, detail: { status: 'error', pregnancyId: record.id, message: 'Unavailable' } })
  assert.doesNotMatch(text(tree), /cached secret|fresh notes/)
  nodes(tree).find(n => n.type === 'button' && text(n).includes('Reintentar detalle')).props.onClick(); assert.equal(onOpen.length, 2)
})
test('unknown history identity and malformed request ids cannot issue GET', async () => {
  const e = env(); await e.ready({ canWrite: false }, [record]); const before = e.calls.length
  await e.history().props.onOpenDetail(id(999)); assert.equal(e.calls.length, before)
  await assert.rejects(e.service.getPregnancyDetail('bad', animal.id, breeding.id, 'token')); assert.equal(e.calls.length, before)
})
