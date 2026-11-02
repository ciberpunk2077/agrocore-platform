import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Button, Card, EmptyState, Field, Input, Select } from '../../ui/components'
import type { DrillRow } from '../drilldown'

export default function DrilldownResults({ rows, expected, mothers = false }: { rows: DrillRow[]; expected: number; mothers?: boolean }) {
  const [query, setQuery] = useState(''), [status, setStatus] = useState(''), [date, setDate] = useState('')
  const [view, setView] = useState<'table' | 'cards'>('table'), [page, setPage] = useState(1)
  const normalize = (value: string) => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('es').trim()
  const filtered = rows.filter(r => (!status || r.status === status) && (!date || r.date === date)
    && normalize([r.animal, ...r.cells.map(c => c.value)].join(' ')).includes(normalize(query)))
  const statuses = [...new Set(rows.map(r => r.status))]
  const pages = Math.max(1, Math.ceil(filtered.length / 24)), currentPage = Math.min(page, pages)
  const visible = filtered.slice((currentPage - 1) * 24, currentPage * 24)
  const uniqueCount = new Set(rows.map(r => r.animalId)).size
  const uniqueLabel = mothers ? (uniqueCount === 1 ? 'madre distinta' : 'madres distintas') : (uniqueCount === 1 ? 'animal distinto' : 'animales distintos')
  const link = (r: DrillRow) => <Link to={`/animals/${r.animalId}`} aria-label={`Ver expediente de ${r.animal}`}>Ver expediente</Link>
  return <>
    <p className="drill-count">{rows.length} {rows.length === 1 ? 'registro' : 'registros'} · {uniqueCount} {uniqueLabel}. Coincide con el KPI consultado: {expected} {expected === 1 ? 'registro' : 'registros'}.</p>
    <p className="drill-note">Las consultas son independientes y los datos pueden cambiar. Los expedientes de animales archivados pueden no estar disponibles.</p>
    <Card className="drill-filters"><Field id="drill-search" label="Buscar en los registros">{a => <Input {...a} type="search" value={query} onChange={e => { setQuery(e.target.value); setPage(1) }} />}</Field>
      {statuses.length > 1 && <Field id="drill-status" label="Estado o situación">{a => <Select {...a} value={status} onChange={e => { setStatus(e.target.value); setPage(1) }}><option value="">Todos</option>{statuses.map(s => <option key={s}>{s}</option>)}</Select>}</Field>}
      <Field id="drill-date" label="Fecha del registro o programada">{a => <Input {...a} type="date" value={date} onChange={e => { setDate(e.target.value); setPage(1) }} />}</Field>
      <Button variant="ghost" onClick={() => { setQuery(''); setStatus(''); setDate(''); setPage(1) }}>Limpiar filtros</Button>
    </Card>
    <div className="drill-toolbar"><p role="status">{filtered.length} resultados de {rows.length} registros</p><div role="group" aria-label="Vista de registros"><Button aria-pressed={view === 'table'} variant={view === 'table' ? 'primary' : 'secondary'} onClick={() => setView('table')}>Tabla</Button><Button aria-pressed={view === 'cards'} variant={view === 'cards' ? 'primary' : 'secondary'} onClick={() => setView('cards')}>Tarjetas</Button></div></div>
    {!rows.length ? <EmptyState>No hay registros para este indicador.</EmptyState> : !filtered.length ? <EmptyState>No hay resultados para los filtros.</EmptyState> : <>
      {view === 'table' ? <div className="drill-table-scroll" role="region" aria-label="Registros; tabla desplazable" tabIndex={0}><table><caption>Registros del indicador</caption><thead><tr><th scope="col">{mothers ? 'Madre' : 'Animal'}</th>{rows[0].cells.map(c => <th scope="col" key={c.label}>{c.label}</th>)}<th scope="col">Expediente</th></tr></thead><tbody>{visible.map(r => <tr key={r.key}><th scope="row">{r.animal}</th>{r.cells.map(c => <td key={c.label}>{c.value}</td>)}<td>{link(r)}</td></tr>)}</tbody></table></div> :
        <ul className="drill-cards">{visible.map(r => <li key={r.key}><Card><h2>{r.animal}</h2><dl>{r.cells.map(c => <div key={c.label}><dt>{c.label}</dt><dd>{c.value}</dd></div>)}</dl>{link(r)}</Card></li>)}</ul>}
      <nav className="drill-pagination" aria-label="Paginación de registros"><p>Página {currentPage} de {pages} · Mostrando {(currentPage - 1) * 24 + 1}–{Math.min(currentPage * 24, filtered.length)} de {filtered.length}</p><div><Button variant="secondary" disabled={currentPage === 1} onClick={() => setPage(currentPage - 1)}>Anterior</Button><Button variant="secondary" disabled={currentPage === pages} onClick={() => setPage(currentPage + 1)}>Siguiente</Button></div></nav>
    </>}
  </>
}
