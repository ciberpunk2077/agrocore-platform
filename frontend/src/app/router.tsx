import { Navigate, createBrowserRouter } from 'react-router-dom'

import DashboardPage from '../pages/DashboardPage'
import LoginPage from '../pages/LoginPage'

export const router = createBrowserRouter([
  {
    path: '/',
    element: <Navigate to="/login" replace />,
  },
  {
    path: '/login',
    element: <LoginPage />,
  },
  {
    path: '/dashboard',
    element: <DashboardPage />,
  },
  {
    path: '*',
    element: <Navigate to="/login" replace />,
  },
])
