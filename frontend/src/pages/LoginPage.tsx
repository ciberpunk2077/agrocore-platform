import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { login } from '../auth/auth.service'
import { saveSession } from '../auth/session'
import { ApiError } from '../lib/api'

function LoginPage() {
  const navigate = useNavigate()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(event: React.SubmitEvent<HTMLFormElement>) {
    event.preventDefault()

    setError(null)
    setIsSubmitting(true)

    try {
      const response = await login({
        email,
        password,
      })

      saveSession(response)
      navigate('/dashboard', { replace: true })
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setError('Correo electrónico o contraseña incorrectos.')
      } else {
        setError('No fue posible iniciar sesión. Inténtalo nuevamente.')
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <main>
      <h1>AgroCore</h1>
      <h2>Iniciar sesión</h2>

      <form onSubmit={handleSubmit}>
        <div>
          <label htmlFor="email">Correo electrónico</label>
          <input
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />
        </div>

        <div>
          <label htmlFor="password">Contraseña</label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
        </div>

        {error && <p role="alert">{error}</p>}

        <button type="submit" disabled={isSubmitting}>
          {isSubmitting ? 'Iniciando sesión...' : 'Iniciar sesión'}
        </button>
      </form>
    </main>
  )
}

export default LoginPage