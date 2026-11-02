import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import * as jsx from 'react/jsx-runtime'
import { renderToStaticMarkup } from 'react-dom/server'
import { load } from '../breeding/test-support.mjs'

const ui = load('../ui/components.tsx', { 'react/jsx-runtime': jsx })
const presentation = load('../dashboard/presentation.ts', {})
const Icon = load('../dashboard/components/DashboardIcon.tsx', { 'react/jsx-runtime': jsx }).default
const mod = value => ({ __esModule: true, default: value })
const Link = props => jsx.jsx('a', { ...props, href: props.to })
const ShellIcon = load('../components/navigation/ShellIcon.tsx', { 'react/jsx-runtime': jsx }).default
const Card = load('../dashboard/components/SummaryCard.tsx', { 'react/jsx-runtime': jsx, 'react-router-dom': { Link }, '../../ui/components': ui, './DashboardIcon': mod(Icon) }).default
const Distribution = load('../dashboard/components/AnimalDistribution.tsx', { 'react/jsx-runtime': jsx, '../../ui/components': ui, '../presentation': presentation }).default
const Agenda = load('../dashboard/components/UpcomingBirthAgenda.tsx', { 'react/jsx-runtime': jsx, '../../ui/components': ui, '../presentation': presentation, 'react-router-dom': { Link }, './DashboardIcon': mod(Icon) }).default
const FollowUp = load('../dashboard/components/DashboardFollowUp.tsx', { 'react/jsx-runtime': jsx, '../../ui/components': ui, 'react-router-dom': { Link }, './DashboardIcon': mod(Icon), '../../components/navigation/ShellIcon': mod(ShellIcon) }).default
const { animalDistribution, daysRemaining, remainingLabel } = presentation

test('KPI uses UI-1A Card, decorative icon and exact value including zero', () => {
  for (const value of [0, 'Sin datos', '0 kg', '400.125 kg', '12345678901234567890.123456789 kg']) {
    const html = renderToStaticMarkup(Card({ label: 'Peso promedio', value, icon: 'weight' }))
    assert.match(html, /ag-card summary-card/)
    assert.match(html, /aria-label="Peso promedio"/)
    assert.ok(html.includes(String(value)))
    assert.match(html, /aria-hidden="true"/)
    assert.doesNotMatch(html, /nacimiento|variación|tendencia/i)
  }
})

test('interactive KPI remains a native link with accessible count, exact route and unchanged value', () => {
  for (const kind of ['pregnancies', 'births_this_month', 'upcoming_births', 'vaccinations_due']) {
    const html = renderToStaticMarkup(Card({ label: 'Indicador', value: 7, to: `/dashboard/${kind}` }))
    assert.ok(html.includes(`href="/dashboard/${kind}"`)); assert.match(html, /aria-label="Indicador: 7. Ver registros"/)
    assert.match(html, /summary-card__value[^>]*>7/); assert.match(html, /Ver registros/)
    assert.doesNotMatch(html, /<button/)
  }
})
test('distribution derives other states and percentages from the same total', () => {
  const result = animalDistribution(8, 6)
  assert.equal(result.other, 2); assert.equal(result.activePercent, 75); assert.equal(result.otherPercent, 25)
  const html = renderToStaticMarkup(Distribution({ total: 8, active: 6 }))
  assert.match(html, /Otros estados/); assert.match(html, /75 %/); assert.match(html, /25 %/)
  assert.doesNotMatch(html, /Inactivos/)
  assert.match(html, /aria-hidden="true"/)
})
test('zero total exposes two zero quantities and zero percentages without a fake chart', () => {
  const data = animalDistribution(0, 0)
  assert.equal(data.activePercent, 0); assert.equal(data.otherPercent, 0); assert.equal(data.other, 0)
  const html = renderToStaticMarkup(Distribution({ total: 0, active: 0 }))
  assert.match(html, /No hay animales para representar/)
  assert.doesNotMatch(html, /NaN|Infinity|dashboard-distribution__bar/)
})
test('rounding keeps nonzero totals at 100 percent', () => {
  for (const [total, active] of [[3, 1], [7, 3], [1, 1], [5, 0], [Number.MAX_SAFE_INTEGER, 1]]) {
    const value = animalDistribution(total, active)
    assert.equal(Math.round((value.activePercent + value.otherPercent) * 10), 1000)
  }
  assert.equal(animalDistribution(3, 1).activePercent, 33.3)
  assert.equal(animalDistribution(3, 1).otherPercent, 66.7)
})
test('inconsistent counts do not produce negative states or percentages over 100', () => {
  for (const [total, active] of [[1, 2], [0, 1], [-1, 0], [3, -1], [1.5, 1]]) assert.equal(animalDistribution(total, active), null)
  const html = renderToStaticMarkup(Distribution({ total: 1, active: 2 }))
  assert.match(html, /No es posible representar/)
  assert.doesNotMatch(html, /width:|%/)
})

for (const [today, expected, days] of [
  ['2026-10-12', '2026-10-12', 0], ['2026-10-12', '2026-11-11', 30],
  ['2026-10-12', '2026-11-12', 31], ['2026-10-12', '2026-10-11', -1],
  ['2024-02-28', '2024-03-01', 2], ['2026-02-28', '2026-03-01', 1],
  ['2026-12-31', '2027-01-01', 1], ['0099-12-31', '0100-01-01', 1],
  ['2026-03-07', '2026-03-09', 2], ['2026-10-31', '2026-11-02', 2],
]) test(`civil dates ${today} to ${expected}: ${days} days independent of DST`, () => assert.equal(daysRemaining(expected, today), days))

test('invalid or missing civil dates never use the browser clock', () => {
  for (const today of [null, '', '0000-01-01', '2026-02-29', '2026-1-1', '2026-10-12T00:00:00Z']) assert.equal(daysRemaining('2026-10-12', today), null)
  assert.equal(daysRemaining('2026-04-31', '2026-10-12'), null)
  assert.equal(remainingLabel(null), 'Fecha operativa no disponible')
})
test('agenda retains inclusive today and +30 rows with exact ISO dates and text equivalents', () => {
  const births = [{ animal_id: 'a', animal: 'MADRE HOY', expected_birth: '2026-10-12' }, { animal_id: 'b', animal: 'MADRE 30', expected_birth: '2026-11-11' }]
  const html = renderToStaticMarkup(Agenda({ births, businessToday: '2026-10-12' }))
  assert.match(html, /30 días, inclusive/); assert.match(html, /nacimientos previstos/)
  assert.match(html, /MADRE HOY/); assert.match(html, /MADRE 30/)
  assert.match(html, /Hoy · 0 días/); assert.match(html, /En 30 días/)
  assert.match(html, /dateTime="2026-11-11"/)
  assert.match(html, /href="\/animals\/a"/); assert.match(html, /href="\/animals\/b"/)
  assert.doesNotMatch(html, /<button/)
})
test('agenda days change with business_today and remain unavailable when absent', () => {
  const births = [{ animal_id: 'a', animal: 'MADRE', expected_birth: '2026-10-13' }]
  assert.match(renderToStaticMarkup(Agenda({ births, businessToday: '2026-10-12' })), /En 1 día/)
  assert.match(renderToStaticMarkup(Agenda({ births, businessToday: '2026-10-13' })), /Hoy · 0 días/)
  const html = renderToStaticMarkup(Agenda({ births, businessToday: null }))
  assert.match(html, /Fecha operativa no disponible/); assert.match(html, /2026-10-13/)
})
test('agenda empty state has no invented rows', () => {
  const html = renderToStaticMarkup(Agenda({ births: [], businessToday: '2026-10-12' }))
  assert.match(html, /ag-state--empty/); assert.match(html, /No hay próximos nacimientos/)
  assert.doesNotMatch(html, /<li|<time/)
})
test('presentation has no historical data sources, clock, links or timezone conversions', () => {
  const helpers = readFileSync(new URL('./presentation.ts', import.meta.url), 'utf8')
  assert.doesNotMatch(helpers, /new Date|Date\.now|Date\.parse|fetch\(|localStorage/)
  const page = readFileSync(new URL('../pages/DashboardPage.tsx', import.meta.url), 'utf8')
  assert.match(page, /data-ag-theme="light"/)
  assert.doesNotMatch(page, /tendencia|mes anterior|histórico|href=|<Link/)
  const css = readFileSync(new URL('../pages/DashboardPage.css', import.meta.url), 'utf8')
  assert.match(css, /max-width: 599px/); assert.match(css, /grid-template-columns: minmax\(0, 1fr\)/)
  assert.match(css, /overflow-wrap: anywhere/)
})

test('donut percentage and arc match the same real quantities with a textual legend', () => {
  const html = renderToStaticMarkup(Distribution({ total: 8, active: 6 }))
  assert.match(html, /viewBox="0 0 120 120"/); assert.match(html, /stroke-dasharray="75 100"/)
  assert.match(html, /dashboard-distribution__percentage[^>]*>75 %/)
  assert.match(html, /Activos/); assert.match(html, /Otros estados/); assert.match(html, />2</)
  assert.doesNotMatch(renderToStaticMarkup(Distribution({ total: 0, active: 0 })), /<svg|NaN|Infinity/)
})
test('follow-up uses exact existing counters and only real read-only routes, including zero', () => {
  for (const value of [0, 7]) {
    const html = renderToStaticMarkup(FollowUp({ summary: { vaccinations_due: value, upcoming_births: value } }))
    assert.match(html, /Actividad y seguimiento/)
    assert.ok(html.includes(`<strong>${value}</strong>`))
    for (const path of ['/animals', '/farms', '/lots']) assert.ok(html.includes(`href="${path}"`))
    assert.doesNotMatch(html, /\/new|\/edit|<button|reciente|hace \d|tendencia|variación/i)
  }
})

test('premium presentation adds no requests, clock or invented feed', () => {
  const source = readFileSync(new URL('./components/DashboardFollowUp.tsx', import.meta.url), 'utf8')
  assert.doesNotMatch(source, /fetch\(|getSession|Date\.|useEffect|localStorage|Math\.random/)
  const page = readFileSync(new URL('../pages/DashboardPage.tsx', import.meta.url), 'utf8')
  assert.match(page, /Panel de control ganadero/); assert.match(page, /Resumen integral de la operación/)
  assert.equal((page.match(/getDashboardSummary\(session.access/g) || []).length, 1)
  assert.equal((page.match(/getUpcomingBirths\(session.access/g) || []).length, 1)
})
