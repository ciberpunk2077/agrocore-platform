import { useEffect, useState } from 'react'

import { getSession } from '../auth/session'
import {
  getDashboardSummary,
  getUpcomingBirths,
} from '../dashboard/dashboard.service'
import SummaryCard from '../dashboard/components/SummaryCard'
import type {
  DashboardSummary,
  UpcomingBirth,
} from '../dashboard/types'
import './DashboardPage.css'

function DashboardPage() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  const [upcomingBirths, setUpcomingBirths] = useState<UpcomingBirth[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let isActive = true

    async function loadSummary() {
      const session = getSession()

      if (!session) {
        if (isActive) {
          setError('No hay una sesión activa.')
          setIsLoading(false)
        }

        return
      }

      try {
        const [summaryData, upcomingBirthsData] = await Promise.all([
          getDashboardSummary(session.access),
          getUpcomingBirths(session.access),
        ])

        if (isActive) {
          setSummary(summaryData)
          setUpcomingBirths(upcomingBirthsData)
        }
      } catch {
        if (isActive) {
          setError('No fue posible cargar el resumen del dashboard.')
        }
      } finally {
        if (isActive) {
          setIsLoading(false)
        }
      }
    }

    void loadSummary()

    return () => {
      isActive = false
    }
  }, [])

  if (isLoading) {
    return <p>Cargando dashboard...</p>
  }

  if (error) {
    return <p>{error}</p>
  }

  if (!summary) {
    return <p>No hay información disponible.</p>
  }

  return (
    <section className="dashboard-page">
      <header className="dashboard-page__header">
        <h1>Dashboard</h1>
        <p>Resumen general de la operación</p>
      </header>

      <div className="dashboard-summary">
        <SummaryCard
          label="Total de animales"
          value={summary.total_animals}
        />

        <SummaryCard
          label="Animales activos"
          value={summary.active_animals}
        />

        <SummaryCard
          label="Gestaciones"
          value={summary.pregnancies}
        />

        <SummaryCard
          label="Nacimientos este mes"
          value={summary.births_this_month}
        />

        <SummaryCard
          label="Próximos nacimientos"
          value={summary.upcoming_births}
        />

        <SummaryCard
          label="Vacunaciones pendientes"
          value={summary.vaccinations_due}
        />

        <SummaryCard
          label="Peso promedio"
          value={
            summary.average_weight !== null
              ? `${summary.average_weight} kg`
              : 'Sin datos'
          }
        />
      </div>

      <section className="dashboard-upcoming">
        <h2>Próximos nacimientos</h2>

        {upcomingBirths.length === 0 ? (
          <p className="dashboard-upcoming__empty">
            No hay próximos nacimientos.
          </p>
        ) : (
          <ul>
            {upcomingBirths.map((birth) => (
              <li key={birth.animal_id}>
                {birth.animal} — {birth.expected_birth}
              </li>
            ))}
          </ul>
        )}
      </section>
    </section>
  )
}

export default DashboardPage