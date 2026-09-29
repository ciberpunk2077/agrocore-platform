import { Navigate, createBrowserRouter } from 'react-router-dom'

import ProtectedRoute from '../auth/ProtectedRoute'
import PublicOnlyRoute from '../auth/PublicOnlyRoute'
import AppLayout from '../layouts/AppLayout'
import AnimalDetailPage from '../pages/AnimalDetailPage'
import AnimalsPage from '../pages/AnimalsPage'
import DashboardPage from '../pages/DashboardPage'
import LoginPage from '../pages/LoginPage'
import NewAnimalPage from '../pages/NewAnimalPage'
import EditAnimalPage from '../pages/EditAnimalPage'

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
          {
            path: '/animals/new',
            element: <NewAnimalPage />,
          },
          {
            path: '/animals/:animalId',
            element: <AnimalDetailPage />,
          },
          {
            path: '/animals/:animalId/edit',
            element: <EditAnimalPage />,
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