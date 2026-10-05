import RequireWrite from '../auth/RequireWrite'
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
import NotFoundPage from '../pages/NotFoundPage'
import FarmsPage from '../pages/FarmsPage'
import FarmDetailPage from '../pages/FarmDetailPage'
import NewFarmPage from '../pages/NewFarmPage'
import EditFarmPage from '../pages/EditFarmPage'
import LotsPage from '../pages/LotsPage'
import LotDetailPage from '../pages/LotDetailPage'
import NewLotPage from '../pages/NewLotPage'
import EditLotPage from '../pages/EditLotPage'

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
            path: '/lots',
            element: <LotsPage />,
          },
          {
            path: '/farms/:farmId/lots/new',
            element: <RequireWrite redirectTo="/farms/:farmId"><NewLotPage /></RequireWrite>,
          },
          {
            path: '/lots/:lotId/edit',
            element: <RequireWrite redirectTo="/lots/:lotId"><EditLotPage /></RequireWrite>,
          },
          {
            path: '/lots/:lotId',
            element: <LotDetailPage />,
          },
          {
            path: '/farms',
            element: <FarmsPage />,
          },
          {
            path: '/farms/new',
            element: <RequireWrite redirectTo="/farms"><NewFarmPage /></RequireWrite>,
          },
          {
            path: '/farms/:farmId/edit',
            element: <RequireWrite redirectTo="/farms/:farmId"><EditFarmPage /></RequireWrite>,
          },
          {
            path: '/farms/:farmId',
            element: <FarmDetailPage />,
          },
          {
            path: '/animals',
            element: <AnimalsPage />,
          },
          {
            path: '/animals/new',
            element: <RequireWrite redirectTo="/animals"><NewAnimalPage /></RequireWrite>,
          },
          {
            path: '/animals/:animalId',
            element: <AnimalDetailPage />,
          },
          {
            path: '/animals/:animalId/edit',
            element: <RequireWrite redirectTo="/animals/:animalId"><EditAnimalPage /></RequireWrite>,
          },
        ],
      },
    ],
  },
  {
    path: '*',
    element: <NotFoundPage />,
  },
])
