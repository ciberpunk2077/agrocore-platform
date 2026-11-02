export interface NavigationItem {
  label: string
  path: string
  icon: 'dashboard' | 'animals' | 'farms' | 'lots'
  group: 'Resumen' | 'Inventario'
}

export const mainNavigation: NavigationItem[] = [
  {
    label: 'Dashboard',
    path: '/dashboard',
    icon: 'dashboard',
    group: 'Resumen',
  },
  {
    label: 'Animales',
    path: '/animals',
    icon: 'animals',
    group: 'Inventario',
  },
  {
    label: 'Fincas',
    path: '/farms',
    icon: 'farms',
    group: 'Inventario',
  },
  { label: 'Lotes', path: '/lots', icon: 'lots', group: 'Inventario' },
]
