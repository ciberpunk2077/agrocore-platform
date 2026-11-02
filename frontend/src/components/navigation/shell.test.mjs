import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import * as react from 'react'
import * as jsx from 'react/jsx-runtime'
import { MemoryRouter, NavLink } from 'react-router-dom'
import { renderToStaticMarkup } from 'react-dom/server'
import { load, harness, nodes, text } from '../../breeding/test-support.mjs'

const navigation = load('../app/navigation.ts', {})
const Icon = load('../components/navigation/ShellIcon.tsx', { 'react/jsx-runtime': jsx }).default
const context = { currentUser: { first_name: 'Ana', last_name: 'López', email: 'ana@example.com' }, currentOrganization: { id: 'org-a', name: 'Finca Esmeralda' }, currentRole: 'VIEWER', canRead: true }
const mod = value => ({ __esModule: true, default: value })
const read = path => readFileSync(new URL(path, import.meta.url), 'utf8')

function sidebarEnv(initialContext = context) {
  const h = harness(), location = { key: 'first' }, events = [], listeners = new Set()
  let desktop = false, closes = 0
  const media = { get matches() { return desktop }, addEventListener(_event, fn) { listeners.add(fn) }, removeEventListener(_event, fn) { listeners.delete(fn) } }
  const Sidebar = load('../components/navigation/Sidebar.tsx', { react: h.react, 'react/jsx-runtime': jsx,
    'react-router-dom': { NavLink, useLocation: () => location }, '../../app/navigation': navigation,
    '../../auth/current-context': { useCurrentContext: () => initialContext }, './ShellIcon': mod(Icon) },
  { window: { matchMedia: () => media } }).default
  const props = { open: false, onClose: () => { closes++ }, menuButtonRef: { current: { focus: () => events.push('trigger-focus') } } }
  const dialog = { open: false, showModal() { this.open = true; events.push('show-modal') }, close() { this.open = false; events.push('close-dialog') } }
  function render(open = props.open) { props.open = open; return h.render(Sidebar, props) }
  const first = render(), dialogNode = nodes(first).find(n => n.type === 'dialog')
  dialogNode.props.ref.current = dialog
  nodes(first).find(n => n.type === 'button').props.ref.current = { focus: () => events.push('close-focus') }
  closes = 0
  return { render, dialog, events, location, h, props, closes: () => closes,
    resize(value) { desktop = value; listeners.forEach(fn => fn()) }, listeners }
}

test('navigation only includes four real read routes and valid groups/icons', () => {
  assert.deepEqual(Array.from(navigation.mainNavigation, item => item.path), ['/dashboard', '/animals', '/farms', '/lots'])
  const router = read('../../app/router.tsx')
  for (const item of navigation.mainNavigation) {
    assert.ok(router.includes(`path: '${item.path}'`))
    assert.ok(['Resumen', 'Inventario'].includes(item.group))
    assert.ok(item.icon)
  }
})
for (const role of ['VIEWER', 'ADMIN']) test(`${role} sees existing read navigation and organization without write controls`, () => {
  const e = sidebarEnv({ ...context, currentRole: role }), tree = e.render()
  assert.match(text(tree), /Finca Esmeralda/)
  const links = nodes(tree).filter(n => n.type === NavLink)
  assert.equal(links.length, 8) // Desktop and closed native dialog; only one is visible.
  assert.doesNotMatch(text(tree), /Crear|Guardar|Pesajes|Reportes/)
  e.h.unmount()
})
test('no READ permission exposes no navigation links', () => {
  const e = sidebarEnv({ ...context, canRead: false })
  assert.equal(nodes(e.render()).filter(n => n.type === NavLink).length, 0)
  e.h.unmount()
})
test('missing organization uses an honest fallback', () => {
  const e = sidebarEnv({ ...context, currentOrganization: null })
  assert.match(text(e.render()), /Sin organización actual/)
  e.h.unmount()
})
for (const route of ['/dashboard', '/animals/animal-a/edit', '/farms/farm-a', '/lots/lot-a']) test(`NavLink marks the active route and nested routes: ${route}`, () => {
  const item = navigation.mainNavigation.find(item => route.startsWith(item.path))
  const e = sidebarEnv(), link = nodes(e.render()).find(n => n.type === NavLink && n.props.to === item.path)
  const html = renderToStaticMarkup(react.createElement(MemoryRouter, { initialEntries: [route] }, link))
  assert.match(html, /aria-current="page"/)
  assert.match(html, /ag-sidebar__link--active/)
  assert.equal(link.props.className({ isActive: false }), 'ag-sidebar__link')
  e.h.unmount()
})
test('opening uses showModal and puts focus on close; closing restores trigger focus', () => {
  const e = sidebarEnv()
  e.render(true)
  assert.equal(e.dialog.open, true)
  assert.deepEqual(e.events, ['show-modal', 'close-focus'])
  e.render(false)
  assert.deepEqual(e.events.slice(-2), ['close-dialog', 'trigger-focus'])
  e.h.unmount()
})
test('Escape cancellation requests controlled close', () => {
  const e = sidebarEnv(), tree = e.render(true)
  let prevented = false
  nodes(tree).find(n => n.type === 'dialog').props.onCancel({ preventDefault() { prevented = true } })
  assert.equal(prevented, true)
  assert.equal(e.closes(), 1)
  e.render(false)
  assert.equal(e.events.at(-1), 'trigger-focus')
  e.h.unmount()
})
test('close button, link navigation and backdrop request close', () => {
  const e = sidebarEnv(), tree = e.render(true)
  nodes(tree).find(n => n.type === 'button').props.onClick()
  nodes(tree).find(n => n.type === NavLink).props.onClick()
  const dialog = nodes(tree).find(n => n.type === 'dialog')
  const target = {}
  dialog.props.onClick({ target, currentTarget: target })
  dialog.props.onClick({ target: {}, currentTarget: target })
  assert.equal(e.closes(), 3)
  e.h.unmount()
})
test('history location changes close drawer without remounting domain content', () => {
  const e = sidebarEnv()
  e.render(true); e.location.key = 'back-navigation'; e.render(true)
  assert.equal(e.closes(), 1)
  e.h.unmount()
})
test('desktop resize closes mobile dialog and listeners clean up', () => {
  const e = sidebarEnv()
  e.render(true); e.resize(true)
  assert.equal(e.closes(), 1)
  e.render(false)
  assert.equal(e.dialog.open, false)
  e.render(true)
  assert.equal(e.dialog.open, false)
  e.h.unmount(); assert.equal(e.listeners.size, 0)
})

function headerEnv(data = context) {
  const calls = [], onMenuOpen = () => calls.push('menu')
  const Header = load('../components/navigation/Header.tsx', { 'react/jsx-runtime': jsx,
    'react-router-dom': { useNavigate: () => (...args) => calls.push(args) },
    '../../auth/session': { clearSession: () => calls.push('clear-session') },
    '../../auth/current-context': { useCurrentContext: () => data }, './ShellIcon': mod(Icon) }).default
  return { calls, tree: Header({ menuOpen: true, onMenuOpen, menuButtonRef: { current: null } }) }
}
test('Header exposes full user, organization and role with accessible truncation', () => {
  const { tree } = headerEnv()
  assert.match(text(tree), /Ana López/); assert.match(text(tree), /ana@example.com/)
  assert.match(text(tree), /Finca Esmeralda/); assert.match(text(tree), /VIEWER/)
  assert.ok(nodes(tree).some(n => n.props.title === 'Ana López'))
  assert.ok(nodes(tree).some(n => n.props.title === 'Finca Esmeralda'))
})
test('menu button connects to drawer and reports expanded state', () => {
  const { tree, calls } = headerEnv(), button = nodes(tree).find(n => n.props['aria-controls'])
  assert.equal(button.type, 'button'); assert.equal(button.props.type, 'button')
  assert.equal(button.props['aria-expanded'], true)
  assert.equal(button.props['aria-controls'], 'ag-navigation-drawer')
  assert.ok(button.props['aria-label']); button.props.onClick(); assert.deepEqual(calls, ['menu'])
})
test('logout still clears session then replaces navigation to login', () => {
  const { tree, calls } = headerEnv()
  nodes(tree).find(n => n.type === 'button' && text(n) === 'Cerrar sesión').props.onClick()
  assert.equal(calls[0], 'clear-session')
  assert.equal(calls[1][0], '/login'); assert.equal(calls[1][1].replace, true)
})
test('logout remains available without a resolved user', () => {
  const { tree } = headerEnv({ ...context, currentUser: null })
  assert.match(text(tree), /Cerrar sesión/)
})
test('AppLayout keeps provider and a single unkeyed Outlet while drawer toggles', () => {
  const h = harness(), Provider = () => null, Header = () => null, Sidebar = () => null, Outlet = () => null
  const Layout = load('../layouts/AppLayout.tsx', { react: h.react, 'react/jsx-runtime': jsx,
    'react-router-dom': { Outlet }, './MainScrollManager': mod(() => null), '../components/navigation/Header': mod(Header),
    '../components/navigation/Sidebar': mod(Sidebar), '../auth/CurrentContextProvider': mod(Provider) }).default
  let tree = h.render(Layout, {})
  assert.equal(tree.type, Provider)
  const outlet = nodes(tree).find(n => n.type === Outlet)
  nodes(tree).find(n => n.type === Header).props.onMenuOpen()
  tree = h.render(Layout, {})
  assert.equal(nodes(tree).find(n => n.type === Header).props.menuOpen, true)
  assert.equal(nodes(tree).find(n => n.type === Outlet).key, outlet.key)
  assert.equal(nodes(tree).filter(n => n.type === Outlet).length, 1)
  nodes(tree).find(n => n.type === Sidebar).props.onClose()
  tree = h.render(Layout, {})
  assert.equal(nodes(tree).find(n => n.type === Header).props.menuOpen, false)
  assert.equal(nodes(tree).find(n => n.type === 'main').props.id, 'ag-main-content')
  h.unmount()
})
test('shell CSS scopes tokens, breakpoint, overflow and light domain area', () => {
  const layout = read('../../layouts/AppLayout.css'), sidebar = read('./Sidebar.css'), header = read('./Header.css')
  for (const css of [layout, sidebar, header]) assert.match(css, /max-width: 767px/)
  assert.match(layout, /248px minmax\(0, 1fr\)/)
  assert.match(layout, /overflow-x: auto/)
  assert.match(layout, /color-scheme: light/)
  assert.match(sidebar, /calc\(100vw - 24px\)/)
  assert.match(sidebar, /prefers-reduced-motion/)
  assert.match(sidebar, /var\(--ag-surface\)/)
  assert.match(header, /background: #103e34/)
  for (const css of [sidebar, header]) assert.match(css, /:focus-visible/)
})
test('icons are decorative and never enter keyboard navigation', () => {
  for (const name of ['leaf', 'menu', 'close', 'dashboard', 'animals', 'farms', 'lots', 'logout', 'user']) {
    const svg = Icon({ name })
    assert.equal(svg.props['aria-hidden'], true); assert.equal(svg.props.focusable, 'false')
  }
})

test('premium header derives initials from real names without repeating organization', () => {
  const { tree } = headerEnv()
  const avatar = nodes(tree).find(n => n.props.className === 'app-header__avatar')
  assert.equal(text(avatar), 'AL'); assert.equal(avatar.props['aria-hidden'], true)
  assert.equal(text(tree).split('Finca Esmeralda').length - 1, 1)
  assert.match(text(tree), /ORGANIZACIÓN ACTIVA/)
  const logout = nodes(tree).find(n => n.type === 'button' && text(n) === 'Cerrar sesión')
  assert.equal(logout.props.type, 'button')
})

test('missing names use a decorative profile icon rather than fabricated initials', () => {
  const { tree } = headerEnv({ ...context, currentUser: { ...context.currentUser, first_name: '', last_name: '' } })
  const avatar = nodes(tree).find(n => n.props.className === 'app-header__avatar')
  assert.equal(text(avatar), '')
  assert.equal(avatar.props.children.props.name, 'user')
  assert.match(text(tree), /ana@example.com/)
})

test('DEMO shell gives banner and header intrinsic rows, leaving only content flexible', () => {
  const h = harness(), Provider = () => null, Header = () => null, Sidebar = () => null, Outlet = () => null
  const Layout = load('../layouts/AppLayout.tsx', { react: h.react, 'react/jsx-runtime': jsx,
    'react-router-dom': { Outlet }, './MainScrollManager': mod(() => null), '../components/navigation/Header': mod(Header),
    '../components/navigation/Sidebar': mod(Sidebar), '../auth/CurrentContextProvider': mod(Provider) }, { __AGROCORE_DEMO__: true }).default
  const tree = h.render(Layout, {})
  const shell = tree.props.children
  const children = shell.props.children.flat().filter(node => node && node.props?.className !== 'ag-shell-skip')
  assert.equal(children[0].props.className, 'ag-demo-banner')
  assert.equal(children[1].type, Header)
  assert.equal(children[2].props.className, 'app-shell__body')
  assert.match(read('../../layouts/AppLayout.css'), /\.app-shell:has\(> \.ag-demo-banner\)\s*\{\s*grid-template-rows: auto auto minmax\(0, 1fr\);/)
})
