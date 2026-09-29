export interface NavigationItem {
  label: string
  path: string
}

export const mainNavigation: NavigationItem[] = [
  {
    label: 'Dashboard',
    path: '/dashboard',
  },
  {
    label: 'Animales',
    path: '/animals',
  },
]
