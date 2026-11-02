import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useCurrentContext } from '../auth/current-context'
import { useSession } from '../auth/useSession'
import { getSessionRevision } from '../auth/session'
import { getAnimal } from '../animals/animals.service'
import { isAnimal, isUUID } from '../breeding/validation'
import type { Animal } from '../animals/types'
import AnimalForm from '../animals/components/form/AnimalForm'
import { PreviewIcon } from '../animals/components/form/AnimalPreviewFields'
import './AnimalEditPreviewPage.css'

export default function AnimalEditPreviewPage() {
  const { animalId } = useParams<{ animalId: string }>()
  const context = useCurrentContext()
  const { session, revision } = useSession()
  if (!animalId || !isUUID(animalId)) return <p role="alert">Identificador de animal inválido.</p>
  if (context.status !== 'loaded') return <p role="status">Cargando contexto...</p>
  if (!context.currentOrganization || !context.canRead || !session) return <p role="alert">No tienes acceso a una organización activa.</p>
  return <Preview key={`${revision}:${context.currentOrganization.id}:${animalId}`} animalId={animalId}
    token={session.access} revision={revision} organizationId={context.currentOrganization.id}
    organizationName={context.currentOrganization.name}
    isCurrentOrganization={context.isCurrentOrganization} />
}

function Preview({ animalId, token, revision, organizationId, organizationName, isCurrentOrganization }: {
  animalId: string; token: string; revision: number; organizationId: string; organizationName: string; isCurrentOrganization: (id: string) => boolean
}) {
  const [state, setState] = useState<{ status: 'loading' | 'error' | 'loaded'; animal: Animal | null }>({ status: 'loading', animal: null })
  const [attempt, setAttempt] = useState(0)
  const current = useCallback(() => getSessionRevision() === revision && isCurrentOrganization(organizationId), [revision, organizationId, isCurrentOrganization])
  useEffect(() => {
    let alive = true
    getAnimal(animalId, token).then(animal => {
      if (!isAnimal(animal, animalId)) throw new Error('Animal no confirmado.')
      if (alive && current()) setState({ status: 'loaded', animal })
    }).catch(() => {
      if (alive && current()) setState({ status: 'error', animal: null })
    })
    return () => { alive = false }
  }, [animalId, token, current, attempt])
  return <section className="animal-edit-preview">
    <header className="animal-edit-preview__header">
      <span className="animal-preview-icon animal-edit-preview__pencil"><PreviewIcon name="pencil" /></span>
      <div className="animal-edit-preview__heading"><div><h1>Editar animal</h1><span className="animal-edit-preview__badge"><PreviewIcon name="lock" />Vista previa · Solo lectura</span></div>
        {state.animal && <p>{state.animal.internal_id || state.animal.official_tag || state.animal.name || animalId} · {state.animal.species || 'Sin datos'}{organizationName ? ` · ${organizationName}` : ''}</p>}
      </div>
      <Link className="animal-edit-preview__close" to={`/animals/${animalId}`} aria-label="Volver al expediente">×</Link>
    </header>
    {state.status === 'loading' && <p role="status">Cargando animal...</p>}
    {state.status === 'error' && <div><p role="alert">No fue posible cargar el animal. Puede no existir o no pertenecer a tu organización.</p><button type="button" onClick={() => { setState({ status: 'loading', animal: null }); setAttempt(v => v + 1) }}>Reintentar consulta</button></div>}
    {state.status === 'loaded' && state.animal && <AnimalForm animal={state.animal} organizationName={organizationName} readOnly />}
    <footer className="animal-edit-preview__footer">
      <div className="animal-edit-preview__notice"><span aria-hidden="true">i</span><div><strong>Vista previa de edición</strong><p>Estás viendo los datos actuales del animal. Los campos están deshabilitados y esta vista no permite guardar cambios.</p></div></div>
      <div className="animal-edit-preview__actions"><Link to={`/animals/${animalId}`}>× <span>Cancelar / Volver al expediente</span></Link><button type="button" disabled>Guardar cambios</button></div>
    </footer>
  </section>
}
