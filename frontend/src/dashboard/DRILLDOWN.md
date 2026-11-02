# Dashboard: detalles de indicadores

Rutas de solo lectura: `/dashboard/pregnancies`, `/dashboard/births_this_month`, `/dashboard/upcoming_births`, `/dashboard/vaccinations_due`. Todas están bajo ProtectedRoute y AppLayout; el indicador se valida contra una lista cerrada. Ningún parámetro selecciona organización. Se conserva sesión, tenant y fecha operativa del contexto, cuya vigencia se comprueba antes de publicar.

## Semántica auditada

- Gestaciones: registros de Pregnancy activos, confirmados, status ACTIVE; animal y breeding de la organización. No cuenta animales únicos.
- Nacimientos del mes: registros de Birth activos cuyo birth_date coincide con año/mes operativo. Incluye vivos y no vivos. Madre, pregnancy y calf (si existe) deben pertenecer al tenant. No equivale a número de crías.
- Próximos nacimientos: registros de gestación activos, confirmados, ACTIVE y expected_birth en hoy..hoy+30 inclusive. El endpoint `/dashboard/upcoming-births` aplica exactamente el mismo predicado. Puede repetir animal; no se deduplica.
- Vacunaciones pendientes: registros activos con next_application_date no nula y <= business_today, animal del tenant. No representa todas las aplicaciones futuras, ni un conteo de animales únicos. Vencida/Vence hoy describe únicamente la fecha programada.

## Fuentes y comprobaciones

Se reutilizan `/dashboard/summary`, `/dashboard/upcoming-births`, GET `/pregnancies/`, `/births/`, `/vaccinations/`, `/breeding/` y `/animals/parents/candidates`. Los listados son completos, sin paginación del servidor. Se filtra toda la respuesta y se pagina localmente (24); cambiar vistas o filtros no realiza consultas.

Los listados de registros no incluyen tenant de las FKs. Antes de publicar se comprueba que las relaciones elegibles aparecen en las consultas autorizadas del tenant. Los candidatos de animales incluyen inactivos no eliminados; no se depende del inventario de animales activos. No se usa un UUID como nombre.

Limitación deliberada: el KPI puede contar relaciones archivadas/eliminadas que las fuentes de consulta no exponen. Si no se puede verificar alguna relación, no se presenta una muestra parcial como equivalente. Tampoco se publica una lista si su cantidad difiere del contador. Las consultas no son una transacción de lectura: los cambios concurrentes pueden requerir actualización. La agenda se contrasta además con la ventana civil del contexto vigente.

No se integran Total de animales/Animales activos en esta fase: el filtro de estado del inventario usa IDs y etiquetas, sin código ACTIVE que garantice equivalencia exacta. El peso promedio no representa un listado de registros.

Los errores o datos incompletos no se convierten en ceros. Las respuestas tardías se descartan al cambiar revisión, tenant, indicador o fecha. No hay operaciones de escritura ni cambios en servicios de dominio o contratos backend.
