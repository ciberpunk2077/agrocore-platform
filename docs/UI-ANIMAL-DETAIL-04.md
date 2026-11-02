# UI-ANIMAL-DETAIL-04 — Expediente premium en todas las secciones

**Decisión: READY para revisión visual manual.** Lint PASS. Build normal PASS. Build DEMO PASS. Las ocho pruebas del fichero nuevo pasaron también tras el ajuste final de fechas UTC y puntos parciales. Permanece el aviso de bundle superior a 500 kB. No se afirma revisión visual: no se ejecutó navegador ni se inspeccionaron capturas.

## Inspección y reutilización

Se revisaron la ficha, las siete rutas, las estructuras Animal, Vaccination, WeightHistory, ProductionRecord y TimelineEvent, los servicios e historiales existentes, sus detalles/acciones y las pruebas de permisos/recuperación. Se reutilizan todos los controladores y servicios. El diseño aprobado de Información general, encabezado y navegación de siete tarjetas permanece intacto.

Los historiales tabulares conservan su estructura semántica y acciones; el CSS del expediente los presenta como tarjetas con campos etiquetados. No se duplica la colección en una segunda lista. Los encabezados de tabla se mantienen para lectores de pantalla y las tarjetas conservan roles explícitos. Las ordenaciones afectan copias de presentación, nunca arrays usados por los controles de edición/reconciliación.

## Por sección

| Sección | Presentación |
|---|---|
| Información general | Sin cambios en el componente ni CSS premium aprobado |
| Salud y vacunaciones | Tarjetas por aplicación, fecha descendente, vacuna, dosis y próxima aplicación solo si está almacenada. Detalles existentes conservan lote, veterinario y notas. Sin cálculo de vencimientos o próximas aplicaciones |
| Pesajes | Último peso por fecha cuando es único, historial en tarjetas, método disponible y gráfica SVG sobre el historial ya cargado. No hay petición adicional para las gráficas |
| Reproducción | Tres bloques con iconos: servicios reproductivos, gestaciones y partos. Historias y detalles existentes, con estados/fechas/resultados reales y estados vacíos. No se fabrican registros según el sexo |
| Movimientos | Tarjetas cronológicas con tipo del catálogo, fecha, origen, destino, motivo y acciones existentes. Datos ausentes conservan sus mensajes explícitos; no se infieren ubicaciones |
| Producción | Tarjetas con fecha/hora UTC, tipo, cantidad, unidad y notas. Gráficas separadas por UUID de tipo y unidad exacta almacenada; sin sumas ni conversiones entre unidades. Rechaza registros de otro animal antes de mostrar tarjetas/gráficas |
| Historial / Timeline | Línea vertical, fechas descendentes, iconos distintos para los seis tipos existentes y un icono neutro para tipos desconocidos; descripción real conservada. Carga, error, vacío y reintento existentes |

## Componentes reutilizables

- `RecordChart`: SVG accesible con título, descripción de puntos, ejes/fechas/unidad, valores originales disponibles en tarjetas y coordenadas temporales proporcionales al tiempo transcurrido.
- `record-chart.ts`: validación pura y ordenación de puntos, sin consultas ni escrituras.
- `WeightOverview`: resumen y gráfica de pesajes usando el mismo historial cargado.
- `ProductionCharts`: partición por tipo y unidad exacta, sin agregaciones.
- `ExpedientBlock`: bloque con icono y título para las tres áreas reproductivas.
- `ExpedientSections.css`: presentación común limitada a las secciones del expediente y sus componentes nuevos; no cambia login, Dashboard ni Información general.

Los formularios presentes antes del cambio siguen usando los mismos handlers, permisos y validaciones; solo se estilizan. No se introdujeron formularios, acciones de escritura, botones de edición ni endpoints nuevos. En DEMO los controles existentes de canWrite/WriteOnly y el bloqueo cliente/proxy siguen vigentes.

## Navegación y alcance

Se conservan `/animals/:animalId` y las seis secciones `/animals/:animalId/{salud,pesajes,reproduccion,movimientos,produccion,historial}`. Siete tarjetas visibles, estado activo, navegación directa, regreso a ficha y regreso a lista. La clave por animal/organización/revisión de sesión y el descarte de respuestas tardías permanecen intactos.

Endpoints existentes (prefijo `/api`), sin modificaciones:
- `/animals/{animal_id}` y contexto `/common/context`.
- `/vaccinations/animal/{animal_id}/history`, detalles de vacunación.
- `/weights/animal/{animal_id}/history`, detalles de pesaje y catálogo de métodos.
- `/breeding/animal/{animal_id}/history`, `/pregnancies/animal/{animal_id}/history`, `/births/animal/{animal_id}/history` y sus detalles/catálogos existentes.
- `/animal-movements/animal/{animal_id}/history`, detalles y catálogos de tipos/fincas/lotes existentes.
- `/production/history/{animal_id}`, detalles y `/catalogs/production-types`.
- `/timeline/animal/{animal_id}`.

## Archivos modificados

- frontend/src/pages/AnimalDetailPage.tsx
- frontend/src/animals/components/AnimalTimeline.tsx
- frontend/src/animals/animal-detail.test.mjs
- frontend/src/vaccinations/components/VaccinationHistory.tsx
- frontend/src/weights/components/WeightHistory.tsx
- frontend/src/breeding/components/BreedingHistory.tsx
- frontend/src/pregnancy/components/PregnancyHistory.tsx
- frontend/src/births/components/BirthHistory.tsx
- frontend/src/animal-movements/components/AnimalMovementHistory.tsx
- frontend/src/production/components/ProductionHistory.tsx

## Archivos creados

- frontend/src/animals/components/RecordChart.tsx
- frontend/src/animals/components/WeightOverview.tsx
- frontend/src/animals/components/ProductionCharts.tsx
- frontend/src/animals/components/ExpedientBlock.tsx
- frontend/src/animals/components/ExpedientSections.css
- frontend/src/animals/record-chart.ts
- frontend/src/animals/expedient.test.mjs
- docs/UI-ANIMAL-DETAIL-04.md

## Pruebas y límites

Pruebas específicas iniciales: 20/20 PASS. Suite completa: 858/858 PASS. Comprobación final del fichero nuevo: 8/8 PASS, incluidos puntos parciales/nulos. Las pruebas cubren datos completos, parciales y vacíos, valores cero, fechas inválidas, empates, tiempos reales en el eje X, separación por tipo/unidad, identidad del animal, permisos de vacunación, orden cronológico, iconos, conservación de navegación/aislamiento y reglas responsive. Los tests existentes siguen comprobando escritura autorizada, bloqueo DEMO, recuperación, errores y cambios de sesión. No se accedió a bases persistentes.

Responsive: tarjetas en dos columnas amplias, una en pantallas intermedias, campos apilados en móvil estrecho y Timeline compacto. Las gráficas tienen desplazamiento horizontal interno cuando hace falta para conservar etiquetas legibles sin ensanchar la página. Foco de teclado preservado en links, botones y detalles.

Limitaciones:
- Las gráficas requieren al menos dos puntos válidos con instantes distintos; fechas duplicadas impiden la gráfica para no inventar un orden. Sin datos suficientes aparece una explicación, no una gráfica ficticia.
- No hay interpolación de mediciones faltantes; las líneas solo unen los puntos registrados. Los valores decimales originales se conservan en tarjetas y descripciones; la geometría SVG usa números JavaScript.
- Con varios pesajes en la fecha más reciente se muestra Sin datos en el resumen y se conservan todos los registros; no se afirma cuál fue el último dentro del día.
- Producción sin unidad almacenada no genera gráfica. Si falla el catálogo se conserva UUID/cantidad/unidad de los registros y se muestra la incidencia existente.
- Timeline depende del selector backend existente y no incluye producción; no se sintetizaron esos eventos en frontend.
- No se afirma una validación visual manual ni cobertura por capturas de navegador. Queda pendiente revisar escritorio, tablet, móvil y lectores de pantalla en el entorno de uso.
- Sin cambios backend, bases, JWT, permisos o configuración normal/DEMO. Sin migraciones, seeds, grants, dependencias nuevas ni Git.
