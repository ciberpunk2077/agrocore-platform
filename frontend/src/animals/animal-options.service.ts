import { apiRequest } from '../lib/api'
import type {
  AnimalStatus,
  Breed,
  Farm,
  Gender,
  Lot,
  Species,
} from './types'

export function getSpecies(accessToken: string): Promise<Species[]> {
  return apiRequest<Species[]>('/catalogs/species', {
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  })
}

export function getBreeds(accessToken: string): Promise<Breed[]> {
  return apiRequest<Breed[]>('/catalogs/breeds', {
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  })
}

export function getGenders(accessToken: string): Promise<Gender[]> {
  return apiRequest<Gender[]>('/catalogs/genders', {
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  })
}

export function getAnimalStatuses(
  accessToken: string,
): Promise<AnimalStatus[]> {
  return apiRequest<AnimalStatus[]>('/catalogs/animal-statuses', {
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  })
}

export function getFarms(accessToken: string): Promise<Farm[]> {
  return apiRequest<Farm[]>('/farms/', {
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  })
}

export function getLots(accessToken: string): Promise<Lot[]> {
  return apiRequest<Lot[]>('/lots/', {
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  })
}