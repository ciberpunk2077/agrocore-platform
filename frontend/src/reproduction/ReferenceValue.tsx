import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { getSession, getSessionRevision } from '../auth/session'
import { resolveReference, type ReferenceKind } from './references'

export default function ReferenceValue({ kind, id, animalId, label, children, secondary = false }: {
  kind: ReferenceKind; id: string; animalId?: string; label?: string; children: ReactNode; secondary?: boolean
}) {
  const [resolved, setResolved] = useState<string | null>(null)
  useEffect(() => {
    if (label) return
    const session = getSession(), revision = getSessionRevision(), controller = new AbortController()
    if (session) void resolveReference(kind, id, animalId, session.access, controller.signal)
      .then(value => { if (!controller.signal.aborted && revision === getSessionRevision()) setResolved(value) })
      .catch(() => { /* Unresolvable does not mean the relationship does not exist. */ })
    return () => controller.abort()
  }, [kind, id, animalId, label])
  if (!label && !resolved) return children
  return <span className="repro-reference"><span>{label ?? resolved}</span>
    {secondary && <small className="repro-reference__id">Referencia: {id}</small>}</span>
}
