import * as react from 'react'
import * as jsx from 'react/jsx-runtime'
import { load } from '../breeding/test-support.mjs'

export const labelImports = { './reference-labels': load('../reproduction/reference-labels.ts', {}) }
const reference = load('../reproduction/ReferenceValue.tsx', {
  react, 'react/jsx-runtime': jsx,
  '../auth/session': { getSession: () => null, getSessionRevision: () => 1 },
  './references': load('../reproduction/references.ts', { ...labelImports, '../breeding/breeding.service': {} }),
})
export const detailImports = {
  '../../reproduction/RecordDetail': load('../reproduction/RecordDetail.tsx', {
    ...labelImports, 'react/jsx-runtime': jsx, './ReferenceValue': reference,
  }, { document: { getElementById: () => null } }),
}
