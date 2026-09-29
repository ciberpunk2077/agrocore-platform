import { Navigate, createBrowserRouter } from 'react-router-dom'

import ProtectedRoute from '../auth/ProtectedRoute'
import PublicOnlyRoute from '../auth/PublicOnlyRoute'
import AppLayout from '../layouts/AppLayout'
import AnimalsPage from '../pages/AnimalsPage'
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
        element: <AppLayout />,
        children: [
          {
            path: '/dashboard',
            element: <DashboardPage />,
          },
          {
            path: '/animals',
            element: <AnimalsPage />,
          },
        ],
      },
    ],
  },
  {
    path: '*',
    element: <Navigate to="/login" replace />,
  },
])