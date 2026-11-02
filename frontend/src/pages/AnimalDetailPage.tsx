import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import WriteOnly from '../auth/WriteOnly'
import { useCurrentContext } from '../auth/current-context'
import { useSession } from '../auth/useSession'
import { getSessionRevision } from '../auth/session'
import { getAnimal } from '../animals/animals.service'
import type { Animal } from '../animals/types'
import { isAnimal, isUUID } from '../breeding/validation'
import { animalSections, animalSectionPath } from '../animals/animal-detail'
import { getLatestAnimalWeight } from '../animals/animal-detail.service'
import AnimalTimeline from '../animals/components/AnimalTimeline'
import AnimalGeneralInformation from '../animals/components/AnimalGeneralInformation'
import ExpedientBlock from '../animals/components/ExpedientBlock'
import DashboardIcon from '../dashboard/components/DashboardIcon'
import WeightHistory from '../weights/components/WeightHistory'
import WeightForm from '../weights/components/WeightForm'
import AnimalMovements from '../animal-movements/components/AnimalMovements'
import Vaccinations from '../vaccinations/components/Vaccinations'
import Breeding from '../breeding/components/Breeding'
import Pregnancy from '../pregnancy/components/Pregnancy'
import Births from '../births/components/Births'
import ProductionHistory from '../production/components/ProductionHistory'
import './AnimalDetailPage.css'
import '../animals/components/ExpedientSections.css'

function AnimalDetailPage() {
  const { animalId, section } = useParams<{ animalId: string; section?: string }>()
  const context = useCurrentContext()
  const { session, revision } = useSession()
  if (!animalId || !isUUID(animalId)) return <p role="alert">Identificador de animal inválido.</p>
  if (section && !animalSections.some(item => item.slug === section)) return <p role="alert">Sección no disponible.</p>
  if (context.status !== 'loaded') return <p role="status">Cargando contexto...</p>
  if (!context.currentOrganization || !context.canRead || !session) return <p role="alert">No hay acceso a una organización activa.</p>
  return <AnimalDetail key={`${revision}:${context.currentOrganization.id}:${animalId}:${section ?? ''}`}
    animalId={animalId} section={section} accessToken={session.access} revision={revision}
    organizationId={context.currentOrganization.id} organizationName={context.currentOrganization.name}
    isCurrentOrganization={context.isCurrentOrganization}
    businessToday={context.businessTimeReady ? context.businessTimeLease?.snapshot.business_today ?? null : null} />
}

type DetailProps = { animalId: string; section?: string; accessToken: string; revision: number; organizationId: string;
  organizationName: string; isCurrentOrganization: (id: string) => boolean; businessToday: string | null }

function AnimalDetail({ animalId, section, accessToken, revision, organizationId, organizationName, isCurrentOrganization, businessToday }: DetailProps) {
  const [state, setState] = useState<{ status: 'loading' | 'error' | 'loaded'; animal: Animal | null }>({ status: 'loading', animal: null })
  const [attempt, setAttempt] = useState(0)
  const [weight, setWeight] = useState<string | null>(null)
  const [weightStatus, setWeightStatus] = useState<'loading' | 'loaded' | 'error'>('loading')
  const [weightHistoryVersion, setWeightHistoryVersion] = useState(0)
  const [pregnancyVersion, setPregnancyVersion] = useState(0)
  const current = useCallback(() => revision === getSessionRevision() && isCurrentOrganization(organizationId), [revision, organizationId, isCurrentOrganization])

  useEffect(() => {
    let alive = true
    getAnimal(animalId, accessToken).then(animal => {
      if (!isAnimal(animal, animalId)) throw new Error('Respuesta de animal inválida.')
      if (alive && current()) setState({ status: 'loaded', animal })
    }).catch(() => {
      if (alive && current()) setState({ status: 'error', animal: null })
    })
    return () => { alive = false }
  }, [animalId, accessToken, current, attempt])

  useEffect(() => {
    if (section || state.status !== 'loaded') return
    const controller = new AbortController()
    getLatestAnimalWeight(animalId, accessToken, controller.signal).then(value => {
      if (!controller.signal.aborted && current()) { setWeight(value); setWeightStatus('loaded') }
    }).catch(() => {
      if (!controller.signal.aborted && current()) setWeightStatus('error')
    })
    return () => controller.abort()
  }, [animalId, accessToken, current, section, state.status, weightHistoryVersion])

  if (state.status === 'loading') return <p role="status">Cargando animal...</p>
  if (state.status === 'error' || !state.animal) return <div><Link to="/animals">Volver a animales</Link><p role="alert">No fue posible cargar el animal. Puede no existir o no pertenecer a tu organización.</p><button type="button" onClick={() => { setState({ status: 'loading', animal: null }); setAttempt(v => v + 1) }}>Reintentar</button></div>
  const animal = state.animal
  const display = (value: string | null | undefined) => value?.trim() || 'Sin datos'
  const title = animal.internal_id?.trim() || animal.official_tag?.trim() || animal.name?.trim() || animal.id
  const selected = section ? animalSections.find(item => item.slug === section) : undefined


  return <section className="animal-detail">
    <div className="animal-detail__back-links">
      <Link className="animal-detail__back" to="/animals">← Volver a animales</Link>
      {section && <Link className="animal-detail__back" to={animalSectionPath(animalId)}>← Volver a la ficha</Link>}
    </div>
    <header className="animal-detail__header">
      <div><p className="animal-detail__eyebrow">Ficha individual del animal</p><h1>{title}</h1>
        <p>{display(animal.species)} <span aria-hidden="true">·</span> {organizationName}</p>
        <div className="animal-detail__badges"><span>{display(animal.status)}</span><span>{animal.is_active ? 'Activo' : 'Inactivo'}</span></div>
      </div>
      <div className="animal-detail__header-actions">
        <Link className="animal-detail__edit" to={animalSectionPath(animalId, 'edit-preview')}>Vista previa de edición</Link>
        <WriteOnly><Link className="animal-detail__edit" to={animalSectionPath(animalId, 'edit')}>Editar animal</Link></WriteOnly>
      </div>
    </header>
    <nav className="animal-detail__nav" aria-label="Secciones del animal">
      {animalSections.map(item => <Link className="animal-detail__nav-card" key={item.slug} to={animalSectionPath(animalId, item.slug)} aria-current={item.slug === (section ?? '') ? 'page' : undefined}>
        <span className="animal-detail__nav-icon"><DashboardIcon name={item.icon} /></span><strong>{item.label}</strong><span>{item.description}</span>
      </Link>)}
    </nav>
    {!section && <section className="animal-detail__card" aria-labelledby="animal-general-heading">
      <h2 id="animal-general-heading">Información general</h2>
      {weightStatus === 'error' && <p className="animal-detail__notice" role="status">Sin datos de último peso: no fue posible confirmar un pesaje único. Consulta Pesajes.</p>}
      <AnimalGeneralInformation animal={animal} businessToday={businessToday} weight={weight} weightStatus={weightStatus} />
    </section>}
    {selected && <section className="animal-detail__module" aria-labelledby="animal-module-heading">
      <h2 id="animal-module-heading"><DashboardIcon name={selected.icon} />{selected.label}</h2>
      {section === 'salud' && <Vaccinations animalId={animalId} birthDate={animal.birth_date} />}
      {section === 'pesajes' && <><WriteOnly><WeightForm animalId={animalId} onSaved={() => setWeightHistoryVersion(v => v + 1)} /></WriteOnly><WeightHistory key={weightHistoryVersion} animalId={animalId} birthDate={animal.birth_date} /></>}
      {section === 'reproduccion' && <>
        <ExpedientBlock title="Servicios reproductivos" icon="calendar"><Breeding animal={animal} /></ExpedientBlock>
        <ExpedientBlock title="Gestaciones" icon="pregnancy"><Pregnancy animal={animal} refreshVersion={pregnancyVersion} /></ExpedientBlock>
        <ExpedientBlock title="Partos" icon="birth"><Births animal={animal} onPregnancyChanged={() => setPregnancyVersion(v => v + 1)} /></ExpedientBlock>
      </>}
      {section === 'movimientos' && <AnimalMovements animalId={animalId} animal={animal} onAnimalUpdated={updated => {
        if (current() && isAnimal(updated, animalId)) setState({ status: 'loaded', animal: updated })
      }} />}
      {section === 'produccion' && <ProductionHistory animalId={animalId} />}
      {section === 'historial' && <AnimalTimeline animalId={animalId} accessToken={accessToken} current={current} />}
    </section>}
  </section>
}

export default AnimalDetailPage
