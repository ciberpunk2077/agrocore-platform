import type { ButtonHTMLAttributes, HTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from 'react'
import './ui.css'

type Tone = 'neutral' | 'success' | 'warning' | 'danger' | 'info'
type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'
const classes = (...values: (string | undefined)[]) => values.filter(Boolean).join(' ')

export function Button({ variant = 'primary', type = 'button', className, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant }) {
  return <button {...props} type={type} className={classes('ag-button', `ag-button--${variant}`, className)} />
}

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div {...props} className={classes('ag-card', className)} />
}

export function Badge({ tone = 'neutral', className, ...props }: HTMLAttributes<HTMLSpanElement> & { tone?: Tone }) {
  return <span {...props} className={classes('ag-badge', `ag-tone--${tone}`, className)} />
}

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={classes('ag-control', className)} />
}

export function Select({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={classes('ag-control', className)} />
}

export function Textarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={classes('ag-control', 'ag-textarea', className)} />
}

interface FieldProps {
  id: string
  label: ReactNode
  hint?: ReactNode
  error?: ReactNode
  className?: string
  children: (attributes: { id: string; 'aria-describedby'?: string; 'aria-invalid'?: true }) => ReactNode
}

export function Field({ id, label, hint, error, className, children }: FieldProps) {
  const hasHint = hint !== undefined && hint !== null && hint !== ''
  const hasError = error !== undefined && error !== null && error !== ''
  const describedBy = [hasHint ? `${id}-hint` : '', hasError ? `${id}-error` : ''].filter(Boolean).join(' ') || undefined
  return <div className={classes('ag-field', className)}>
    <label className="ag-field__label" htmlFor={id}>{label}</label>
    {children({ id, 'aria-describedby': describedBy, 'aria-invalid': hasError ? true : undefined })}
    {hasHint && <p className="ag-field__hint" id={`${id}-hint`}>{hint}</p>}
    {hasError && <p className="ag-field__error" id={`${id}-error`} role="alert">{error}</p>}
  </div>
}

export function LoadingState({ children = 'Cargando…', className, ...props }: Omit<HTMLAttributes<HTMLDivElement>, 'role'>) {
  return <div {...props} role="status" className={classes('ag-state', 'ag-state--loading', className)}>{children}</div>
}

export function EmptyState({ children = 'No hay datos disponibles.', className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div {...props} className={classes('ag-state', 'ag-state--empty', className)}>{children}</div>
}

export function ErrorState({ children = 'No fue posible cargar los datos.', className, ...props }: Omit<HTMLAttributes<HTMLDivElement>, 'role'>) {
  return <div {...props} role="alert" className={classes('ag-state', 'ag-state--error', className)}>{children}</div>
}
