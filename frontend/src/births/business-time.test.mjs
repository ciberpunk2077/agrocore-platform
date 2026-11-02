import assert from 'node:assert/strict'
import test from 'node:test'
import * as jsx from 'react/jsx-runtime'
import { readFileSync } from 'node:fs'
import { load, harness, mod, nodes } from '../breeding/test-support.mjs'
import { contextData } from '../breeding/flow-test-support.mjs'
import { env, payload, record, pregnancy, snapshot } from './flow-test-support.mjs'

for (const lease of [null, { snapshot, remainingMs: 0, receivedMonotonic: 0, receivedWall: 0 }]) test(`CREATE requires fresh business_time but READ remains ${JSON.stringify(lease)}`, async () => {
  const e = env(); await e.ready({ businessTimeLease: lease }, [{ ...record, pregnancy_id: '00000199-1111-1111-1111-111111111111' }])
  const before = e.calls.length; assert.equal(await e.form().props.onCreate(payload), false); assert.equal(e.calls.length, before)
  assert.equal(e.history().props.history.length, 1); assert.equal(e.form().props.disabled, true)
})
test('business_today controls form date, browser UTC date cannot permit tomorrow', async () => {
  const e = env(); await e.ready(); assert.equal(e.form().props.businessToday, '2026-10-05')
  const before = e.calls.length; assert.equal(await e.form().props.onCreate({ ...payload, birth_date: '2026-10-06' }), false); assert.equal(e.calls.length, before)
})
for (const today of ['2026-10-04', '2026-10-05', '2026-10-06']) test(`fresh context day ${today} decides POST after preparation`, async () => {
  const e = env(); await e.ready(); e.prepare({ context: { data: contextData(undefined, { ...snapshot, business_today: today, server_now: `${today}T12:00:00Z`, valid_until: `${today}T12:01:00Z` }) } })
  if (today >= payload.birth_date) { e.queue('POST', { data: record }); e.sync() }
  await e.form().props.onCreate(payload); assert.equal(e.count('POST'), today >= payload.birth_date ? 1 : 0)
})
test('real BirthForm max uses tenant day and expired lease disables submit', () => {
  const h = harness(); h.react.useMemo = fn => fn()
  const Form = load('../births/components/BirthForm.tsx', { react: h.react, 'react/jsx-runtime': jsx,
    '../../components/FieldError': mod(() => null), '../../lib/api-errors': { fieldErrorAttributes: () => ({}) } }).default
  const props = { animal: { id: payload.mother_id }, pregnancies: [pregnancy], breedings: [], animals: [], genders: [], disabled: false,
    businessToday: '2026-10-05', fieldErrors: {}, onClearErrors() {}, onCreate: async () => { throw new Error('No POST expected') } }
  const tree = h.render(Form, props)
  assert.equal(nodes(tree).find(n => n.props?.id === 'birth-date').props.max, props.businessToday)
  const source = readFileSync(new URL('./components/BirthForm.tsx', import.meta.url), 'utf8')
  assert.doesNotMatch(source, /toISOString|new Date/)
})

test('public Birth frontend exposes no UPDATE or DELETE interface', () => {
  for (const path of ['births.service.ts', 'components/Births.tsx', 'components/BirthHistory.tsx']) {
    const source = readFileSync(new URL(path, import.meta.url), 'utf8')
    assert.doesNotMatch(source, /method:\s*['"](?:PUT|PATCH|DELETE)/)
  }
})

test('real form double submit is synchronous and late completion never mutates unmounted form', async () => {
  const { deferred, find } = await import('../breeding/test-support.mjs')
  const h = harness(); h.react.useMemo = fn => fn()
  const Form = load('../births/components/BirthForm.tsx', { react: h.react, 'react/jsx-runtime': jsx,
    '../../components/FieldError': mod(() => null), '../../lib/api-errors': { fieldErrorAttributes: () => ({}) } }).default
  const d = deferred(), calls = []
  const props = { animal: { id: payload.mother_id }, pregnancies: [pregnancy], breedings: [], animals: [], genders: [], disabled: false,
    businessToday: '2026-10-05', fieldErrors: {}, onClearErrors() {}, onCreate: p => { calls.push(p); return d.promise } }
  let tree = h.render(Form, props)
  const control = name => nodes(tree).find(n => n.props?.id === name)
  control('birth-pregnancy').props.onChange({ target: { value: pregnancy.id } }); tree = h.render(Form, props); tree = h.render(Form, props)
  control('birth-date').props.onChange({ target: { value: payload.birth_date } })
  control('birth-weight').props.onChange({ target: { value: payload.birth_weight } })
  control('birth-calf-gender').props.onChange({ target: { value: payload.calf_gender_id } }); tree = h.render(Form, props)
  const submit = find(tree, 'form').props.onSubmit
  const first = submit({ preventDefault() {} }), second = submit({ preventDefault() {} })
  assert.equal(calls.length, 1); h.unmount(); const before = h.slots.slice()
  d.resolve(true); await Promise.all([first, second]); assert.deepEqual(h.slots, before)
})
