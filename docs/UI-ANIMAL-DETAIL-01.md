# UI-ANIMAL-DETAIL-01 — Ficha individual del animal

Decisión: **READY para revisión visual manual**. No se ejecutó navegador automatizado; las pruebas responsive verifican estructura y reglas CSS, no capturas renderizadas.

## Pantallas y navegación

La lista Animales ya enlazaba a `/animals/:animalId`; se conserva ese acceso. La ficha ahora muestra encabezado, seis tarjetas con iconos e información general. Cada tarjeta abre una sección del mismo animal y ofrece **Volver a la ficha**. No monta las otras secciones ocultas ni sus formularios.

| Ruta | Componentes reutilizados |
|---|---|
| `/animals/:animalId` | Ficha general e iconos existentes DashboardIcon |
| `/animals/:animalId/salud` | Vaccinations |
| `/animals/:animalId/pesajes` | WeightForm y WeightHistory |
| `/animals/:animalId/reproduccion` | Breeding, Pregnancy y Births |
| `/animals/:animalId/movimientos` | AnimalMovements |
| `/animals/:animalId/produccion` | ProductionHistory |
| `/animals/:animalId/historial` | Nueva vista breve de solo lectura AnimalTimeline |

Las secciones usan `/animals/:animalId/:section` con lista explícita de secciones permitidas. La ruta estática de edición conserva RequireWrite y su precedencia. No se crearon seis módulos completos.

## Datos y endpoints

Encabezado: ID interno, arete o nombre con UUID como referencia final; especie, organización del contexto validado, estado e indicador activo/inactivo. Información general: nombre, sexo, raza, nacimiento, edad calculada con fecha operativa válida, último pesaje confirmado, finca, lote, identificadores, peso de nacimiento, madre/padre con referencia histórica y notas. Ausencias: **Sin datos**. Un fallo de consulta muestra error explícito y no datos sustitutos.

Lecturas nuevas o coordinadas por la ficha (prefijo `/api` del cliente existente):

- `/animals/{animal_id}` para validar el animal antes de montar cualquier módulo.
- `/weights/animal/{animal_id}/history` y `/weights/{weight_id}` para el último peso, confirmando animal_id, fecha e importe del pesaje. El historial existente viene por fecha ascendente: se ordena localmente por fecha descendente. Si hay empate en el día más reciente, no se inventa cuál ocurrió después: se muestra Sin datos con explicación y acceso a Pesajes.
- `/timeline/animal/{animal_id}`: contrato real `{ id, date, event_type, title, description }`. Vacío, error y respuesta malformada se distinguen; solo GET.

Los componentes conservan sus servicios y endpoints existentes: historiales y detalles de vaccinations, weights, breeding, pregnancies, births, animal-movements y production; catálogos existentes y operaciones de escritura sujetas a los mismos permisos. No se inventaron endpoints.

Limitación existente de Timeline: su selector agrega pesajes, movimientos, vacunaciones, reproducción, gestaciones y partos; no agrega producción. No se fabricaron esos eventos en la UI.

## Aislamiento y DEMO

La ficha requiere contexto cargado, organización activa, permiso canRead y sesión. Su clave incluye revisión de sesión, organización, animal y sección: un cambio desmonta el ámbito anterior. Respuestas tardías se descartan si la revisión o la organización ya no coinciden. La respuesta de Animal se valida contra el UUID solicitado antes de renderizar datos, links de módulos o formularios. Las consultas auxiliares también comprueban vigencia; Timeline cancela al desmontar.

El contrato de Animal y el de eventos Timeline no incluyen organization_id; el alcance de las respuestas sigue dependiendo de los selectores backend existentes y del JWT. No se afirma una verificación adicional de tenant basada en campos que no existen. El contexto de organización no se toma de URLs manipulables.

Se conserva WriteOnly, RequireWrite y todos los controles de los componentes. En DEMO canWrite sigue siendo false y el cliente/proxy continúan bloqueando escrituras. Timeline no ofrece acciones de escritura. No se cambiaron JWT, permisos, configuración de modos, login, Dashboard, backend ni bases de datos. No se usó Git ni se ejecutaron migraciones o seeds.

## Archivos

Modificados:
- frontend/src/pages/AnimalDetailPage.tsx
- frontend/src/pages/AnimalDetailPage.css
- frontend/src/app/router.tsx

Creados:
- frontend/src/animals/animal-detail.ts
- frontend/src/animals/animal-detail.service.ts
- frontend/src/animals/components/AnimalTimeline.tsx
- frontend/src/animals/animal-detail.test.mjs
- docs/UI-ANIMAL-DETAIL-01.md

## Validación

- Regresión frontend: **846/846 PASS**.
- Pruebas finales específicas: **9/9 PASS**, incluida la prueba adicional de estados vacíos/error y descarte de respuestas de Timeline después de desmontaje o cambio de organización.
- Cobertura: rutas y seis accesos por animal, retorno a ficha, campos vacíos, referencias históricas, animal equivocado, cambios de sesión/organización, edad civil válida, último peso y pertenencia al animal, fechas ambiguas, contrato Timeline, ausencia de escrituras en el servicio nuevo, rejillas responsive, foco visible y wrapping.
- Lint: PASS. Build normal: PASS. Build DEMO: PASS. Los builds conservan el aviso de bundle superior a 500 kB.
- Responsive: seis columnas en escritorio amplio, tres en tablet/escritorio reducido, dos en móvil y una en pantallas estrechas; tablas de componentes existentes dentro de un contenedor con desplazamiento horizontal.

Pendiente: revisión visual manual en navegador, recortes/espaciado en dispositivos reales y prueba interactiva con el backend disponible. No se consultaron bases persistentes para estas pruebas. Los recursos de login que el usuario haya añadido se conservaron intactos.
