import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { login } from '../auth/auth.service'
import { saveSession } from '../auth/session'
import { ApiError } from '../lib/api'
import './LoginPage.css'

const modules = [
  { label: 'Animales', path: 'M4 10 2 5l5 2 5-2 5 2 5-2-2 5v7l-4 3H8l-4-3Zm5 3h.01M15 13h.01M9 17h6' },
  { label: 'Fincas', path: 'm3 10 9-7 9 7M5 9v12h14V9M9 21v-7h6v7M11 7h2' },
  { label: 'Reproducción', path: 'M12 21S2 14 2 8a5 5 0 0 1 10-1 5 5 0 0 1 10 1c0 6-10 13-10 13Zm-7-9h4l2-4 3 8 2-4h3' },
  { label: 'Producción', path: 'M4 21v-8h4v8m2 0V7h4v14m2 0V3h4v18M2 21h20' },
  { label: 'Vacunaciones', path: 'm14 3 7 7m-5-5L5 16l3 3L19 8M3 21l3-3m3-6 3 3M11 10l3 3' },
  { label: 'Y mucho más', path: 'M12 3v2m0 14v2M3 12h2m14 0h2M5.6 5.6 7 7m10 10 1.4 1.4M5.6 18.4 7 17M17 7l1.4-1.4' },
]

function LoginIcon({ path }: { path: string }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={path} /></svg>
}

function LoginPage() {
  const navigate = useNavigate()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [passwordVisible, setPasswordVisible] = useState(false)

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
    <main className="login-page">
      <section className="login-story" aria-label="AgroCore Platform">
        {/* Reserved for the user's standalone photograph; no screenshot or substitute image. */}
        <div className="login-photo" aria-hidden="true" />
        <div className="login-story__content">
          <div className="login-brand" aria-label="AgroCore Platform">
            <svg className="login-brand__mark" viewBox="0 0 56 64" aria-hidden="true">
              <path fill="currentColor" d="M30 39C24 19 34 5 52 2c1 20-6 33-22 37ZM26 49C8 48 2 37 3 22c17 1 27 11 23 27Z" />
              <path d="M27 61V36L42 17M27 48 12 32" fill="none" stroke="#063d2b" strokeWidth="3" strokeLinecap="round" />
            </svg>
            <div><div className="login-brand__name">Agro<span>Core</span></div><div className="login-brand__platform">PLATFORM</div></div>
          </div>
          <h1>El control de tu ganadería,<br /><span>en un solo lugar.</span></h1>
          <p className="login-story__description">Gestiona animales, fincas, reproducción,<br className="login-desktop-break" /> producción y mucho más.</p>
        </div>
        <ul className="login-modules" aria-label="Módulos de AgroCore">
          {modules.map(module => <li key={module.label}><LoginIcon path={module.path} /><span>{module.label}</span></li>)}
        </ul>
      </section>

      <section className="login-access" aria-labelledby="login-heading">
        {__AGROCORE_DEMO__ && <div className="login-demo" role="status"><span className="login-demo__dot" />DEMO <span>· Solo lectura</span></div>}
        <div className="login-card">
          <h2 id="login-heading">Bienvenido a <span>AgroCore</span></h2>
          <p className="login-card__intro">Inicia sesión en tu cuenta para continuar.</p>

      <form className="login-form" onSubmit={handleSubmit} aria-busy={isSubmitting}>
        <div className="login-field">
          <label htmlFor="email">Correo electrónico</label>
          <div className="login-input">
          <LoginIcon path="M3 6h18v12H3z m0 0 9 7 9-7" />
          <input
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
            placeholder="correo@ejemplo.com"
            autoCapitalize="none"
            spellCheck={false}
          />
          </div>
        </div>

        <div className="login-field">
          <label htmlFor="password">Contraseña</label>
          <div className="login-input">
          <LoginIcon path="M5 10h14v11H5zM8 10V7a4 4 0 0 1 8 0v3M12 14v3" />
          <input
            id="password"
            name="password"
            type={passwordVisible ? 'text' : 'password'}
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
            placeholder="Ingresa tu contraseña"
          />
          <button className="login-password-toggle" type="button" aria-label={passwordVisible ? 'Ocultar contraseña' : 'Mostrar contraseña'} aria-pressed={passwordVisible} onClick={() => setPasswordVisible(value => !value)}>
            <LoginIcon path={passwordVisible ? 'm3 3 18 18M10.5 10.5a2 2 0 0 0 3 3M9 5.5a11 11 0 0 1 12 6.5 14 14 0 0 1-4 4M6.5 6.5A14 14 0 0 0 2 12s4 7 10 7a11 11 0 0 0 5-1' : 'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Zm13 0a3 3 0 1 1-6 0 3 3 0 0 1 6 0'} />
          </button>
          </div>
        </div>

        {error && <p className="login-error" role="alert">{error}</p>}

        <button className="login-submit" type="submit" disabled={isSubmitting}>
          {isSubmitting ? 'Iniciando sesión...' : 'Iniciar sesión'}
          <LoginIcon path="M5 12h14m-5-5 5 5-5 5" />
        </button>
      </form>
      <div className="login-card__divider" aria-hidden="true"><span /></div>
      <p className="login-security"><LoginIcon path="M6 10h12v11H6zM9 10V7a3 3 0 0 1 6 0v3M12 14v3" />Acceso seguro a AgroCore Platform</p>
      </div>
      </section>
    </main>
  )
}

export default LoginPage
