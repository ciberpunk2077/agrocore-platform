import type { SVGProps } from 'react'

type IconName = 'dashboard' | 'animals' | 'farms' | 'lots' | 'leaf' | 'menu' | 'close' | 'logout' | 'user'
const paths: Record<IconName, string> = {
  dashboard: 'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
  animals: 'M6 8 3 5v6l3 2 M18 8l3-3v6l-3 2 M6 8h12v10l-3 3H9l-3-3z M9 14h.01 M15 14h.01 M10 18h4',
  farms: 'M3 11 12 3l9 8 M5 10v11h14V10 M10 21v-7h4v7',
  lots: 'M3 3h18v18H3z M3 12h18 M12 3v18',
  leaf: 'M20 4C9 2 3 8 5 15c2 7 15 6 15-11Z M5 20 16 9',
  menu: 'M4 6h16 M4 12h16 M4 18h16',
  close: 'm6 6 12 12 M18 6 6 18',
  logout: 'M9 4H4v16h5 M10 12h11m-4-4 4 4-4 4',
  user: 'M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0ZM4 21v-2a8 8 0 0 1 16 0v2',
}

export default function ShellIcon({ name, ...props }: SVGProps<SVGSVGElement> & { name: IconName }) {
  return <svg {...props} className="ag-shell-icon" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden={true} focusable="false"><path d={paths[name]} /></svg>
}
