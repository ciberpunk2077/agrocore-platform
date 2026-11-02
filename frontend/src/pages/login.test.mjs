import assert from 'node:assert/strict'
import test from 'node:test'
import * as jsx from 'react/jsx-runtime'
import { renderToStaticMarkup } from 'react-dom/server'
import { load, harness, nodes, find } from '../breeding/test-support.mjs'

function setup(demo, authenticate = async () => ({ access: 'test-only' })) {
  const hooks = harness(), saved = [], navigated = []
  class ApiError extends Error { constructor(status) { super('Test error'); this.status = status } }
  const Page = load('../pages/LoginPage.tsx', {
    react: hooks.react, 'react/jsx-runtime': jsx,
    'react-router-dom': { useNavigate: () => (...args) => navigated.push(args) },
    '../auth/auth.service': { login: authenticate },
    '../auth/session': { saveSession: value => saved.push(value) },
    '../lib/api': { ApiError },
  }, { __AGROCORE_DEMO__: demo }).default
  const render = () => hooks.render(Page)
  return { render, saved, navigated, ApiError }
}

test('login uses real accessible fields and DEMO badge only in DEMO', () => {
  for (const demo of [false, true]) {
    const html = renderToStaticMarkup(setup(demo).render())
    assert.equal(html.includes('DEMO'), demo)
    assert.match(html, /type="email"/)
    assert.match(html, /type="password"/)
    assert.match(html, /autoComplete="current-password"/)
    assert.match(html, /required=""/)
    assert.doesNotMatch(html, /<img|data:image|background-image/)
  }
})

test('login preserves credentials submission, session and dashboard navigation', async () => {
  const requests = []
  const page = setup(true, async credentials => { requests.push(credentials); return { access: 'test-only' } })
  let tree = page.render()
  nodes(tree).find(n => n.props?.id === 'email').props.onChange({ target: { value: 'fake@example.invalid' } })
  nodes(tree).find(n => n.props?.id === 'password').props.onChange({ target: { value: 'fake-test-only' } })
  tree = page.render()
  await find(tree, 'form').props.onSubmit({ preventDefault() {} })
  assert.equal(requests[0].email, 'fake@example.invalid')
  assert.equal(requests[0].password, 'fake-test-only')
  assert.equal(page.saved.length, 1)
  assert.equal(page.navigated[0][0], '/dashboard')
  assert.equal(page.navigated[0][1].replace, true)
})

test('visibility toggle never submits and retains the entered password', () => {
  const page = setup(false)
  let tree = page.render()
  nodes(tree).find(n => n.props?.id === 'password').props.onChange({ target: { value: 'fake-test-only' } })
  const toggle = nodes(tree).find(n => n.props?.['aria-label'] === 'Mostrar contraseña')
  assert.equal(toggle.props.type, 'button')
  toggle.props.onClick()
  tree = page.render()
  const field = nodes(tree).find(n => n.props?.id === 'password')
  assert.equal(field.props.type, 'text')
  assert.equal(field.props.value, 'fake-test-only')
  assert.equal(page.saved.length, 0)
})

test('failed authentication exposes an alert and never saves a session', async () => {
  const page = setup(false, async () => { throw new page.ApiError(401) })
  await find(page.render(), 'form').props.onSubmit({ preventDefault() {} })
  const tree = page.render()
  assert.ok(nodes(tree).some(n => n.props?.role === 'alert'))
  assert.equal(page.saved.length, 0)
  assert.equal(page.navigated.length, 0)
})
