import { detailImports } from '../reproduction/test-support.mjs'
import assert from 'node:assert/strict'
import test from 'node:test'
import * as jsx from 'react/jsx-runtime'
import { load, harness, tick, deferred, text, button, nodes, mod } from '../breeding/test-support.mjs'
import { id } from '../breeding/flow-test-support.mjs'
import { env, newAbortProtocol, newProtocol, animal, breeding, payload, record, historyPath } from './flow-test-support.mjs'
const path = r => `/api/pregnancies/${r.id}`
const aborted = { ...record, status: 'ABORTED' }
const other = { ...record, id: id(155), breeding_id: id(156) }
const scope = e => e.protocol.attemptKey(e.props.revision, e.props.organizationId, e.props.animal.id)
const attempt = e => e.abortProtocol.getAbortAttempt(scope(e))
async function ready(e, extra = {}, rows = [record]) { await e.ready(extra, rows) }
function prep(e, fresh = record) { e.queue(path(record), { data: fresh }) }
function sync(e, rows = [aborted]) { e.sync(rows) }

test('cancelled confirmation sends neither preparation GET nor POST', async () => {
  const e = env(); await ready(e); e.confirm(false); const before = e.calls.length
  await e.history().props.onAbort(record); assert.equal(e.calls.length, before); assert.equal(attempt(e), undefined)
})
for (const role of ['OWNER', 'ADMIN', 'VETERINARIAN', 'OPERATOR']) {
  test(`${role} uses fresh ACTIVE GET then one bodyless POST, preserves history and breeding reservation without business_time`, async () => {
    const e = env(); await ready(e, { businessTimeLease: null }); e.context({ currentRole: role })
    prep(e); e.queue('POST', { data: aborted }); sync(e)
    const before = e.calls.length; await e.history().props.onAbort(record); e.render()
    assert.equal(e.calls[before].path, path(record)); assert.equal(e.calls[before].cache, 'no-store')
    const post = e.calls.find(c => c.method === 'POST'); assert.equal(post.path, `${path(record)}/abort`); assert.equal(post.body, undefined)
    assert.equal(e.count('POST'), 1); assert.equal(e.calls.filter(c => c.path === '/api/common/context').length, 0)
    assert.match(text(e.tree()), /aborto ya fue registrado/); assert.equal(e.history().props.history[0].status, 'ABORTED')
    assert.equal(e.history().props.history[0].breeding_id, breeding.id); assert.equal(e.form(), undefined)
    assert.equal(attempt(e), undefined)
  })
}
test('VIEWER handler rejects before confirmation or preparation', async () => {
  const e = env(); await ready(e, { canWrite: false, businessTimeLease: null }); const before = e.calls.length
  await e.history().props.onAbort(record); assert.equal(e.calls.length, before); assert.equal(e.count('POST'), 0)
})
test('stale handler sees live permission change before preparation', async () => {
  const e = env(); await ready(e); const old = e.history().props.onAbort
  e.render({ canWrite: false }); await old(record); assert.equal(e.count('POST'), 0); assert.equal(attempt(e), undefined)
})
for (const fresh of [null, {}, { ...record, id: id(999) }, { ...record, animal_id: id(999) }, { ...record, breeding_id: id(999) },
  { ...record, diagnosis_date: '2026-02-30' }, { ...record, notes: 42 }]) {
  test(`invalid preparation ${JSON.stringify(fresh)} => no POST`, async () => {
    const e = env(); await ready(e); prep(e, fresh); await e.history().props.onAbort(record); e.render()
    assert.equal(e.count('POST'), 0); assert.equal(attempt(e), undefined); assert.ok(e.history())
  })
}
for (const status of ['FINISHED', 'ABORTED']) {
  test(`fresh ${status} reconciles history and never POSTs stale ACTIVE`, async () => {
    const e = env(); await ready(e); prep(e, { ...record, status }); sync(e, [{ ...record, status }])
    await e.history().props.onAbort(record); e.render(); assert.equal(e.count('POST'), 0)
    assert.equal(e.history().props.history[0].status, status); assert.match(text(e.tree()), /ya no está ACTIVE/)
    await e.history().props.onAbort({ ...record, status }); assert.equal(e.count('POST'), 0)
  })
}
for (const status of [403, 404, 500]) {
  test(`preparation GET ${status} is not POST uncertainty`, async () => {
    const e = env(); await ready(e); e.queue(path(record), { status }); await e.history().props.onAbort(record); e.render()
    assert.equal(e.count('POST'), 0); assert.equal(attempt(e), undefined); assert.doesNotMatch(text(e.tree()), /Resultado incierto del aborto/)
  })
}
test('double click freezes target and fresh record; mutating UI cannot redirect POST to Y', async () => {
  const e = env(); await ready(e, {}, [record, other]); const d = deferred(), input = { ...record }
  e.queue(path(record), () => d.promise); e.queue('POST', { data: aborted }); sync(e)
  const handler = e.history().props.onAbort, work = handler(input)
  input.id = other.id; input.breeding_id = other.breeding_id; await handler(other); await handler(record)
  assert.equal(Object.isFrozen(attempt(e).target), true); assert.equal(attempt(e).target.pregnancyId, record.id)
  d.resolve({ data: record }); await work; assert.equal(e.count('POST'), 1); assert.equal(e.calls.find(c => c.method === 'POST').path, `${path(record)}/abort`)
})
for (const change of ['session', 'organization', 'animal', 'permission', 'unmount']) {
  test(`${change} during preparation => no POST or stale state`, async () => {
    const e = env(); await ready(e); const d = deferred(); e.queue(path(record), () => d.promise)
    const work = e.history().props.onAbort(record); await tick(); e.render()
    if (change === 'session') e.changeSession()
    if (change === 'organization') e.context({ currentOrganization: { id: id(999) } })
    if (change === 'permission') e.render({ canWrite: false })
    if (change === 'animal' || change === 'unmount') e.h.unmount()
    d.resolve({ data: record }); await work; assert.equal(e.count('POST'), 0)
    e.h.unmount(); assert.equal(attempt(e), undefined)
  })
}
for (const change of [{ id: id(999) }, { animal_id: id(999) }, { breeding_id: id(999) }, { status: 'ACTIVE' }, { status: 'FINISHED' },
  { diagnosis_date: '2026-10-04' }, { expected_birth: '2027-02-01' }, { confirmed: false }, { notes: 'changed' }, { notes: 1 }]) {
  test(`POST semantic mismatch ${JSON.stringify(change)} => uncertain`, async () => {
    const e = env(); await ready(e); prep(e); e.queue('POST', { data: { ...aborted, ...change } })
    await e.history().props.onAbort(record); e.render(); assert.equal(attempt(e).phase, 'uncertain')
    assert.match(text(e.tree()), /Resultado incierto del aborto/); assert.doesNotMatch(text(e.tree()), /aborto ya fue registrado/)
    await e.history().props.onAbort(record); assert.equal(e.count('POST'), 1)
  })
}
for (const response of [{ data: null }, { data: {} }, { status: 202, data: aborted }, { status: 204, data: null }, { status: 500 }, { status: 503 },
  new TypeError('network'), Object.assign(new TypeError('timeout'), { name: 'AbortError' })]) {
  test(`ambiguous POST ${JSON.stringify(response)} blocks all Pregnancy writes and never retries`, async () => {
    const e = env(); await ready(e); prep(e); e.queue('POST', response); await e.history().props.onAbort(record); e.render()
    assert.equal(attempt(e).phase, 'uncertain'); await e.history().props.onAbort(record); assert.equal(e.count('POST'), 1)
    assert.equal(e.history().props.disabled, true)
  })
}
for (const status of [400, 403, 404, 422]) {
  test(`deterministic POST rejection ${status} releases attempt and synchronizes GET only`, async () => {
    const e = env(); await ready(e); prep(e); e.queue('POST', { status, data: { detail: 'Solo se puede abortar una gestación activa.' } }); sync(e, [{ ...record, status: 'FINISHED' }])
    await e.history().props.onAbort(record); e.render(); assert.equal(attempt(e), undefined); assert.equal(e.count('POST'), 1)
    assert.doesNotMatch(text(e.tree()), /Resultado incierto del aborto/); assert.equal(e.history().props.history[0].status, 'FINISHED')
  })
}
test('401 is handled globally; old scope cannot repeat or publish success', async () => {
  const e = env(); await ready(e); prep(e); e.queue('POST', { status: 401 }); await e.history().props.onAbort(record); e.h.unmount()
  assert.equal(attempt(e).phase, 'uncertain'); assert.equal(e.count('POST'), 1)
})
for (const status of ['ABORTED', 'FINISHED', 'ACTIVE', '404']) {
  test(`uncertain recovery ${status} observes backend state without proving authorship or retrying POST`, async () => {
    const e = env(); await ready(e); prep(e); e.queue('POST', { status: 503 }); await e.history().props.onAbort(record); e.render()
    e.queue(path(record), status === '404' ? { status: 404 } : { data: { ...record, status } })
    if (status !== '404') sync(e, [{ ...record, status }])
    const before = e.calls.length; button(e.tree(), 'Consultar resultado del aborto').props.onClick(); button(e.tree(), 'Consultar resultado del aborto').props.onClick()
    await tick(); e.render(); assert.equal(attempt(e).phase, 'uncertain'); assert.equal(e.count('POST'), 1)
    assert.ok(e.calls.slice(before).every(c => !c.method))
    if (status === '404') assert.match(text(e.tree()), /ya no está disponible/)
    else assert.match(text(e.tree()), /no demuestra autoría/)
    await e.history().props.onAbort(record); assert.equal(e.count('POST'), 1)
  })
}
test('confirmed + failed HISTORY refresh keeps confirmed and only GET recovery releases ledger', async () => {
  const e = env(); await ready(e); prep(e); e.queue('POST', { data: aborted }); e.queue(historyPath(animal.id), { status: 503 })
  await e.history().props.onAbort(record); e.render(); assert.equal(attempt(e).phase, 'confirmed'); assert.match(text(e.tree()), /aborto ya fue registrado/)
  e.queue(path(record), { data: aborted }); sync(e)
  button(e.tree(), 'Consultar resultado del aborto').props.onClick(); await tick(); e.render(); assert.equal(attempt(e), undefined); assert.equal(e.count('POST'), 1)
})
test('A to B to A preserves unresolved target and ignores late POST success', async () => {
  const protocol = newProtocol(), abortProtocol = newAbortProtocol(), e = env(protocol, abortProtocol)
  await ready(e); prep(e); const d = deferred(); e.queue('POST', () => d.promise)
  const work = e.history().props.onAbort(record); await tick(); e.h.unmount()
  const b = env(protocol, abortProtocol); await ready(b, { animal: { ...animal, id: id(99) } }, []); b.h.unmount()
  const again = env(protocol, abortProtocol); await ready(again); assert.equal(again.history().props.disabled, true)
  await again.history().props.onAbort(record); assert.equal(again.count('POST'), 0)
  d.resolve({ data: aborted }); await work; again.render(); assert.equal(attempt(again).phase, 'uncertain'); assert.doesNotMatch(text(again.tree()), /aborto ya fue registrado/)
})
test('F5/new ledger reads backend but never submits automatically', async () => {
  const e = env(); await ready(e); prep(e); e.queue('POST', { status: 503 }); await e.history().props.onAbort(record); e.h.unmount()
  const reload = env(); await ready(reload, {}, [aborted]); assert.equal(reload.count('POST'), 0); assert.equal(attempt(reload), undefined)
})
test('DETAIL opening/closing/errors cannot release or redirect ABORT', async () => {
  const e = env(); await ready(e); prep(e); e.queue('POST', { status: 503 }); await e.history().props.onAbort(record); e.render()
  e.queue(path(record), { status: 404 }); await e.history().props.onOpenDetail(record.id); e.render(); e.history().props.onCloseDetail()
  assert.equal(attempt(e).phase, 'uncertain'); await e.history().props.onAbort(record); assert.equal(e.count('POST'), 1)
})
test('CREATE handler cannot start while ABORT is uncertain, even with otherwise ready options', async () => {
  const e = env(); await ready(e, {}, [])
  // A real ACTIVE target appears in refreshed HISTORY after the form was rendered.
  const create = e.form().props.onCreate
  e.sync([record]); button(e.tree(), 'Actualizar eventos disponibles').props.onClick(); await tick(); e.render()
  prep(e); e.queue('POST', { status: 503 }); await e.history().props.onAbort(record)
  assert.equal(await create(payload), false); assert.equal(e.count('POST'), 1)
})
for (const change of ['session', 'organization', 'animal']) {
  test(`late POST after ${change} cannot contaminate another scope`, async () => {
    const e = env(); await ready(e); prep(e); const d = deferred(); e.queue('POST', () => d.promise)
    const work = e.history().props.onAbort(record); await tick(); e.render()
    if (change === 'session') e.changeSession()
    if (change === 'organization') e.context({ currentOrganization: { id: id(999) } })
    e.h.unmount(); const before = e.h.slots.slice()
    const next = env(); await ready(next, { animal: change === 'animal' ? { ...animal, id: id(88) } : animal }, [])
    d.resolve({ data: aborted }); await work; assert.deepEqual(e.h.slots.slice(), before)
    next.render(); assert.doesNotMatch(text(next.tree()), /aborto ya fue registrado|Resultado incierto del aborto/)
  })
}
test('unmount during preparation releases unsent attempt; return can make a deliberate fresh attempt', async () => {
  const registry = newAbortProtocol(), e = env(newProtocol(), registry); await ready(e); const d = deferred()
  e.queue(path(record), () => d.promise); const work = e.history().props.onAbort(record); e.h.unmount()
  const next = env(newProtocol(), registry); await ready(next); assert.equal(attempt(next), undefined)
  d.resolve({ data: record }); await work; assert.equal(e.count('POST'), 0)
  prep(next); next.queue('POST', { data: aborted }); sync(next); await next.history().props.onAbort(record); assert.equal(next.count('POST'), 1)
})
test('uncertain recovery malformed GET never releases ledger or invents success', async () => {
  const e = env(); await ready(e); prep(e); e.queue('POST', { status: 503 }); await e.history().props.onAbort(record); e.render()
  e.queue(path(record), { data: { ...aborted, id: id(999) } }); button(e.tree(), 'Consultar resultado del aborto').props.onClick()
  await tick(); e.render(); assert.equal(attempt(e).phase, 'uncertain'); assert.equal(e.count('POST'), 1); assert.doesNotMatch(text(e.tree()), /aborto ya fue registrado/)
})
test('VIEWER WriteOnly does not render abort controls while retaining READ detail summaries', () => {
  const write = load('../auth/WriteOnly.tsx', { ...detailImports, 'react/jsx-runtime': jsx, './current-context': { useCurrentContext: () => ({ canWrite: false }) } })
  assert.equal(write.default({ children: 'Registrar aborto', fallback: '—' }), '—')
})
test('successful abort releases ACTIVE but keeps consumed breeding excluded for CREATE', async () => {
  const e = env(); await ready(e); prep(e); e.queue('POST', { data: aborted }); sync(e); await e.history().props.onAbort(record); e.render()
  assert.equal(e.form(), undefined); assert.equal(e.history().props.history.length, 1)
  // A distinct breeding becomes eligible; the previously consumed one never does.
  const next = { ...breeding, id: id(200) }
  e.sync([aborted], [breeding, next]); button(e.tree(), 'Actualizar eventos disponibles').props.onClick(); await tick(); e.render()
  assert.deepEqual(Array.from(e.form().props.events, r => r.id), [next.id]); assert.equal(e.form().props.disabled, false)
})
test('abort compares historical notes exactly without trimming or changing them', async () => {
  const e = env(); const fresh = { ...record, notes: '  historical notes  ' }; await ready(e, {}, [fresh]); prep(e, fresh)
  e.queue('POST', { data: { ...fresh, status: 'ABORTED' } }); sync(e, [{ ...fresh, status: 'ABORTED' }])
  await e.history().props.onAbort(fresh); e.render(); assert.match(text(e.tree()), /aborto ya fue registrado/)
})
test('real history offers abort only on ACTIVE + write; FINISHED/ABORTED retain READ details', () => {
  const h = harness(), component = load('../pregnancy/components/PregnancyHistory.tsx', { ...detailImports, 'react/jsx-runtime': jsx, '../../auth/WriteOnly': mod(() => null) })
  const tree = h.render(component.default, { history: [record, { ...other, status: 'FINISHED' }, { ...aborted, id: id(157) }], eventLabels: new Map(),
    disabled: false, onAbort() {}, detail: { status: 'idle' }, onOpenDetail() {}, onCloseDetail() {} })
  assert.equal(nodes(tree).filter(n => n.type === 'button' && text(n).includes('Registrar aborto')).length, 1)
  assert.equal(nodes(tree).filter(n => n.type === 'button' && text(n).includes('Ver detalles')).length, 3)
})
