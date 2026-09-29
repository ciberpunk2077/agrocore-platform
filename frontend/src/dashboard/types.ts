export interface DashboardSummary {
  total_animals: number
  active_animals: number
  pregnancies: number
  births_this_month: number
  upcoming_births: number
  vaccinations_due: number
  average_weight: string | null
}

export interface UpcomingBirth {
  animal_id: string
  animal: string
  expected_birth: string
}