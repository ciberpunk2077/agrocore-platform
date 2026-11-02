import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import * as jsx from 'react/jsx-runtime'
import { renderToStaticMarkup } from 'react-dom/server'
import { load, nodes } from '../breeding/test-support.mjs'

const ui = load('../ui/components.tsx', { 'react/jsx-runtime': jsx })
const tokens = readFileSync(new URL('./tokens.css', import.meta.url), 'utf8')
const css = readFileSync(new URL('./ui.css', import.meta.url), 'utf8')

for (const variant of ['primary', 'secondary', 'ghost', 'danger']) {
  test(`Button ${variant} preserves native attributes and handlers`, () => {
    const onClick = () => {}, ref = { current: null }
    const tree = ui.Button({ variant, className: 'custom', type: 'submit', disabled: true, name: 'save', value: 'yes', id: 'save', 'aria-label': 'Guardar', onClick, ref, children: 'Guardar' })
    assert.equal(tree.type, 'button')
    assert.equal(tree.props.className, `ag-button ag-button--${variant} custom`)
    for (const [key, value] of Object.entries({ type: 'submit', disabled: true, name: 'save', value: 'yes', id: 'save', 'aria-label': 'Guardar', onClick, ref })) assert.equal(tree.props[key], value)
    assert.match(renderToStaticMarkup(tree), /disabled=""/)
  })
}
test('Button defaults to a non-submitting native button', () => assert.equal(ui.Button({}).props.type, 'button'))

for (const tone of ['neutral', 'success', 'warning', 'danger', 'info']) {
  test(`Badge ${tone} exposes text without assuming a live region`, () => {
    const tree = ui.Badge({ tone, className: 'custom', children: 'Estado', title: 'Detalle' })
    assert.equal(tree.type, 'span')
    assert.equal(tree.props.className, `ag-badge ag-tone--${tone} custom`)
    assert.equal(tree.props.role, undefined)
    assert.match(renderToStaticMarkup(tree), />Estado</)
  })
}
test('Card preserves content, landmarks and custom classes', () => {
  const tree = ui.Card({ children: 'Contenido', role: 'region', 'aria-label': 'Resumen', className: 'custom' })
  assert.equal(tree.props.className, 'ag-card custom')
  assert.match(renderToStaticMarkup(tree), /role="region" aria-label="Resumen"/)
})
for (const [name, tag] of [['Input', 'input'], ['Select', 'select'], ['Textarea', 'textarea']]) {
  test(`${name} forwards controlled/native props including accessibility and ref`, () => {
    const onChange = () => {}, ref = { current: null }
    const props = { id: 'control', name: 'control', value: 'value', onChange, disabled: true, required: true, 'aria-describedby': 'help', 'aria-invalid': true, ref, className: 'custom' }
    const tree = ui[name](props)
    assert.equal(tree.type, tag)
    for (const [key, value] of Object.entries(props)) if (key !== 'className') assert.equal(tree.props[key], value)
    assert.match(tree.props.className, /^ag-control/)
    assert.match(tree.props.className, /custom$/)
    assert.match(renderToStaticMarkup(tree), /disabled=""/)
  })
}
test('Field associates label, hint and error with the actual native control', () => {
  const tree = ui.Field({ id: 'animal', label: 'Animal', hint: 'Ayuda', error: 'Requerido', children: attrs => ui.Input({ ...attrs, required: true }) })
  const all = nodes(tree), control = all.find(n => n.type === 'input')
  assert.equal(all.find(n => n.type === 'label').props.htmlFor, control.props.id)
  assert.equal(control.props['aria-invalid'], true)
  assert.equal(control.props['aria-describedby'], 'animal-hint animal-error')
  for (const id of control.props['aria-describedby'].split(' ')) assert.ok(all.some(n => n.props.id === id))
  assert.equal(all.find(n => n.props.id === 'animal-error').props.role, 'alert')
})
test('Field without messages creates no dangling descriptions or invalid state', () => {
  const tree = ui.Field({ id: 'notes', label: 'Notas', children: attrs => ui.Textarea(attrs) })
  const control = nodes(tree).find(n => n.type === 'textarea')
  assert.equal(control.props['aria-describedby'], undefined)
  assert.equal(control.props['aria-invalid'], undefined)
})
for (const [name, role, kind] of [['LoadingState', 'status', 'loading'], ['EmptyState', undefined, 'empty'], ['ErrorState', 'alert', 'error']]) {
  test(`${name} has accessible semantics and accepts custom content`, () => {
    const tree = ui[name]({ children: 'Mensaje', id: 'state', className: 'custom' })
    assert.equal(tree.props.role, role)
    assert.equal(tree.props.id, 'state')
    assert.equal(tree.props.className, `ag-state ag-state--${kind} custom`)
    assert.match(renderToStaticMarkup(tree), /Mensaje/)
    assert.ok(ui[name]({}).props.children)
  })
}

const blocks = [...tokens.matchAll(/\{([^}]+)\}/g)].map(match => Object.fromEntries([...match[1].matchAll(/(--ag-[\w-]+):\s*([^;]+);/g)].map(m => [m[1], m[2].trim()])))
const luminance = hex => {
  const channels = hex.slice(1).match(/../g).map(value => parseInt(value, 16) / 255).map(value => value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4)
  return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722
}
for (const [theme, values] of [['light', blocks[0]], ['dark', { ...blocks[0], ...blocks[1] }]]) {
  test(`${theme} tokens resolve every component variable`, () => {
    for (const match of css.matchAll(/var\((--ag-[\w-]+)\)/g)) assert.ok(values[match[1]], match[1])
  })
  test(`${theme} text and status pairs meet WCAG AA normal text contrast`, () => {
    const pairs = [['text', 'surface'], ['text-secondary', 'surface'], ['text-muted', 'surface'], ['text-muted', 'bg'], ['on-primary', 'primary'], ['on-primary', 'primary-hover'], ['primary', 'surface'], ['disabled-text', 'disabled-bg']]
    for (const tone of ['success', 'warning', 'danger', 'info']) pairs.push([tone, `${tone}-bg`])
    for (const [fg, bg] of pairs) {
      const a = luminance(values[`--ag-${fg}`]), b = luminance(values[`--ag-${bg}`])
      assert.ok((Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05) >= 4.5, `${theme} ${fg}/${bg}`)
    }
  })
  test(`${theme} focus and control boundaries meet non-text contrast`, () => {
    for (const fg of ['focus', 'border']) for (const bg of ['surface', 'bg']) {
      const a = luminance(values[`--ag-${fg}`]), b = luminance(values[`--ag-${bg}`])
      assert.ok((Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05) >= 3, `${theme} ${fg}/${bg}`)
    }
  })
}
test('styles are explicitly scoped, allow small widths, focus and reduced motion', () => {
  assert.match(css, /:focus-visible/)
  assert.match(css, /prefers-reduced-motion: reduce/)
  assert.match(css, /min-width: 0/)
  assert.match(css, /max-width: 100%/)
  assert.match(css, /:disabled/)
  for (const match of css.matchAll(/(?:^|\n)([^{}]+)\{/g)) {
    const selector = match[1].trim()
    if (!selector.startsWith('@')) for (const part of selector.split(',')) assert.ok(part.trim().startsWith('.ag-'), selector)
  }
})
test('demo is isolated from routing, session and production components', () => {
  const demo = readFileSync(new URL('./DesignSystemDemo.tsx', import.meta.url), 'utf8')
  assert.match(demo, /\['light', 'dark'\]/)
  assert.doesNotMatch(demo, /auth\/|service|useEffect|useState/)
  const router = readFileSync(new URL('../app/router.tsx', import.meta.url), 'utf8')
  assert.doesNotMatch(router, /DesignSystemDemo|ui-demo/)
})
