import { Navigate, createBrowserRouter } from 'react-router-dom'

import ProtectedRoute from '../auth/ProtectedRoute'
import PublicOnlyRoute from '../auth/PublicOnlyRoute'
import DashboardPage from '../pages/DashboardPage'
import LoginPage from '../pages/LoginPage'

export const router = createBrowserRouter([
  {
    path: '/',
    element: <Navigate to="/login" replace />,
  },
  {
    element: <PublicOnlyRoute />,
    children: [
      {
        path: '/login',
        element: <LoginPage />,
      },
    ],
  },
  {
    element: <ProtectedRoute />,
    children: [
      {
        path: '/dashboard',
        element: <DashboardPage />,
      },
    ],
  },
  {
    path: '*',
    element: <Navigate to="/login" replace />,
  },
])