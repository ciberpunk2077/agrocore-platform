import type { ReactNode } from 'react'
import DashboardIcon from '../../dashboard/components/DashboardIcon'

export default function ExpedientBlock({ title, icon, children }: { title: string; icon: 'pregnancy' | 'birth' | 'calendar'; children: ReactNode }) {
  return <section className="expedient-block" aria-label={title}>
    <header className="expedient-block__heading"><DashboardIcon name={icon} /><h3>{title}</h3></header>{children}
  </section>
}
