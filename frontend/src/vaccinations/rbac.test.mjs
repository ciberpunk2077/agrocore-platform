import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { runInNewContext } from 'node:vm'
import ts from 'typescript'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

// Exercise the real components with controlled hook state, without a DOM dependency.
function load(path, imports) {
  const source = readFileSync(new URL(path, import.meta.url), 'utf8')
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  })
  const exports = {}
  runInNewContext(outputText, { exports, require(name) {
    if (name.endsWith('.css')) return {}
    assert.ok(name in imports, `Unexpected import: ${name}`)
    return imports[name]
  }, AbortController })
  return exports
}

const animalId = '11111111-1111-1111-1111-111111111111'
const vaccinationId = '22222222-2222-2222-2222-222222222222'
const record = {
  id: vaccinationId, animal_id: animalId, vaccine_name: 'Vacuna de prueba',
  application_date: '2026-01-01', next_application_date: null, dose: '1',
  batch: null, veterinarian: null, notes: null, is_active: true,
}

function components(canWrite, states = []) {
  let index = 0
  const react = { ...React, useEffect() {}, useState(initial) {
    return [index < states.length ? states[index++] : initial, () => {}]
  } }
  const common = {
    react, 'react/jsx-runtime': ReactRuntime,
    '../../auth/session': { getSession() {}, getSessionRevision() {} },
  }
  const WriteOnly = load('../auth/WriteOnly.tsx', {
    'react/jsx-runtime': ReactRuntime,
    './current-context': { useCurrentContext: () => ({ canWrite }) },
  })
  const history = load('./components/VaccinationHistory.tsx', {
    ...common, '../../auth/WriteOnly': WriteOnly, '../vaccinations.service': {},
  }).default
  const preparation = load('./components/VaccinationPreparation.tsx', {
    ...common, '../../auth/WriteOnly': WriteOnly, '../vaccinations.service': {},
    '../../lib/api': {}, '../../lib/api-errors': {},
    './VaccinationEditForm': { __esModule: true, default: () => React.createElement('button', null, 'Guardar cambios') },
  }).default
  return { history, preparation }
}

import * as ReactRuntime from 'react/jsx-runtime'

for (const canWrite of [false, true]) {
  test(`Container gates registration and editing, independently of detail; canWrite=${canWrite}`, () => {
    let index = 0
    // historyVersion, formVersion, result, editingId, viewingId, createBusy, reconciled
    const states = [0, 0, null, null, vaccinationId, false, false]
    const WriteOnly = load('../auth/WriteOnly.tsx', {
      'react/jsx-runtime': ReactRuntime,
      './current-context': { useCurrentContext: () => ({ canWrite }) },
    })
    const container = load('./components/Vaccinations.tsx', {
      '../../auth/current-context': { useCurrentContext: () => ({ currentOrganization: { id: 'tenant-A' } }) },
      react: { ...React, useState: () => [states[index++], () => {}] },
      'react/jsx-runtime': ReactRuntime, '../../auth/WriteOnly': WriteOnly,
      './VaccinationForm': { __esModule: true, default: () => React.createElement('button', null, 'Registrar vacunación') },
      './VaccinationDeleteConfirmation': { __esModule: true, default: () => null },
      './VaccinationHistory': { __esModule: true, default: () => null },
      './VaccinationPreparation': { __esModule: true, default: ({ readOnly }) => React.createElement('p', null, readOnly ? 'Detalle READ' : 'Editar WRITE') },
    }).default
    const html = renderToStaticMarkup(React.createElement(container, { animalId, birthDate: null }))
    assert.ok(html.includes('Detalle READ'))
    assert.equal(html.includes('Registrar vacunación'), canWrite)
    assert.ok(!html.includes('Editar WRITE'))
  })
}

for (const canWrite of [false, true]) {
  test(`History exposes READ with empty optional fields; canWrite=${canWrite}`, () => {
    const { history } = components(canWrite, [[record], false, null, 0])
    const html = renderToStaticMarkup(React.createElement(history, {
      animalId, saved: null, actionsDisabled: false, onEdit() {}, onView() {}, onLoaded() {},
    }))
    assert.match(html, /<th scope="col">Acciones<\/th>/)
    assert.match(html, />Ver detalles<\/button>/)
    assert.equal(html.includes('>Editar</button>'), canWrite)
    assert.equal(html.includes('>Eliminar</button>'), canWrite)
  })

  test(`Detail never exposes a write action; canWrite=${canWrite}`, () => {
    const { preparation } = components(canWrite, [0, { status: 'ready', record }])
    const html = renderToStaticMarkup(React.createElement(preparation, {
      readOnly: true, vaccinationId, animalId, birthDate: null,
      onCancel() {}, onSaved() {}, onRecheck() {},
    }))
    for (const label of ['Vacuna de prueba', 'Fecha de aplicación', 'Próxima aplicación', 'Dosis', 'Lote', 'Veterinario', 'Notas', 'Estado', 'Volver']) {
      assert.ok(html.includes(label), label)
    }
    assert.ok(!html.includes('Guardar cambios'))
  })

  test(`Edit form remains gated; canWrite=${canWrite}`, () => {
    const { preparation } = components(canWrite, [0, { status: 'ready', record }])
    const html = renderToStaticMarkup(React.createElement(preparation, {
      vaccinationId, animalId, birthDate: null, onCancel() {}, onSaved() {}, onRecheck() {},
    }))
    assert.equal(html.includes('Guardar cambios'), canWrite)
  })
}

test('Safe detail uses authenticated GET and rejects a different record or animal', async () => {
  const validation = load('./validation.ts', { './civil-date': {} })
  let response = record
  const calls = []
  const service = load('./vaccinations.service.ts', {
    '../lib/api': { apiRequest: async (...args) => { calls.push(args); return response } },
    '../lib/api-errors': {}, './validation': validation,
  })
  const signal = new AbortController().signal
  assert.equal(await service.getVaccination(vaccinationId, animalId, 'viewer-token', signal), record)
  const [path, options] = calls[0]
  assert.equal(path, `/vaccinations/${vaccinationId}`)
  assert.equal(options.accessToken, 'viewer-token')
  assert.equal(options.signal, signal)
  assert.equal(options.expectedStatus, 200)
  assert.equal(options.method, undefined)
  assert.equal(options.body, undefined)
  response = { ...record, id: animalId }
  await assert.rejects(service.getVaccination(vaccinationId, animalId, 'viewer-token'), /inválida/)
  response = { ...record, animal_id: vaccinationId }
  await assert.rejects(service.getVaccination(vaccinationId, animalId, 'viewer-token'), /inválida/)
})
