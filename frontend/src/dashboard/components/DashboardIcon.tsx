type IconName = 'herd' | 'active' | 'pregnancy' | 'birth' | 'calendar' | 'vaccination' | 'weight' | 'refresh'
const paths: Record<IconName, string> = {
  herd: 'M6 8 3 5v6l3 2 M18 8l3-3v6l-3 2 M6 8h12v10l-3 3H9l-3-3z M9 14h.01 M15 14h.01 M10 18h4',
  active: 'M20 12a8 8 0 1 1-4-7 M8 11l4 4 9-10',
  pregnancy: 'M12 20S3 14 3 8a5 5 0 0 1 9-3 5 5 0 0 1 9 3c0 6-9 12-9 12Z',
  birth: 'M12 3v6 M9 6h6 M5 12a7 7 0 1 0 14 0 M8 14h.01 M16 14h.01 M9 18h6',
  calendar: 'M4 5h16v16H4z M8 3v4 M16 3v4 M4 10h16 M8 14h2 M14 14h2',
  vaccination: 'm16 3 5 5 M14 5l5 5 M5 14l5 5 M3 21l4-4 M6 13l7-7 5 5-7 7z M11 9l2 2',
  weight: 'M4 7h16l2 14H2z M9 7V5a3 3 0 0 1 6 0v2 M12 12v4',
  refresh: 'M20 7v5h-5 M4 17v-5h5 M6 7a7 7 0 0 1 12-1l2 6 M4 12l2 6a7 7 0 0 0 12-1',
}

export default function DashboardIcon({ name }: { name: IconName }) {
  return <svg className="ag-dashboard-icon" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden={true} focusable="false"><path d={paths[name]} /></svg>
}
