import assert from 'node:assert/strict'
import { test } from 'node:test'
import { load } from './breeding/test-support.mjs'

test('DEMO blocks mutations before fetch; permits login and reads', async () => {
  const calls = []
  const { apiRequest } = load('../lib/api.ts', { '../auth/session': { getSessionRevision: () => 0 } }, {
    __AGROCORE_DEMO__: true,
    fetch: async (url, options) => { calls.push([url, options]); return { status: 200, ok: true, json: async () => ({}) } },
  })
  for (const method of ['POST', 'PUT', 'PATCH', 'DELETE']) {
    await assert.rejects(apiRequest('/animals/', { method }))
  }
  assert.equal(calls.length, 0)
  await apiRequest('/auth/login', { method: 'POST', body: '{}' })
  await apiRequest('/animals/')
  assert.equal(calls.length, 2)
  assert.equal(calls[1][1].cache, 'no-store')
})

test('DEMO session keys cannot read or clear normal sessions', () => {
  const storage = new Map([['agrocore.access', 'normal']])
  const session = load('../auth/session.ts', {}, { __AGROCORE_DEMO__: true, localStorage: {
    getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key),
  } })
  assert.equal(session.getSession(), null)
  session.saveSession({ access: 'demo', refresh: 'demo', user: {} })
  session.clearSession()
  assert.equal(storage.get('agrocore.access'), 'normal')
})
