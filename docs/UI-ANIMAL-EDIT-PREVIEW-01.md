# UI-ANIMAL-EDIT-PREVIEW-01 — Formulario real en solo lectura

**Decisión: READY para revisión visual manual.** Suite frontend 864/864 PASS; pruebas específicas finales 18/18 PASS; lint PASS; builds normal y DEMO PASS. Permanece el aviso de bundle superior a 500 kB. No se realizó revisión visual en navegador.

## Inspección

Formulario existente: `frontend/src/animals/components/form/AnimalForm.tsx`, utilizado por NewAnimalPage y EditAnimalPage. La edición normal está en `/animals/:animalId/edit` bajo RequireWrite. Se revisó `backend/apps/animals/api/schemas.py` en modo lectura; no se modificó backend.

AnimalUpdateSchema admite estos **15 campos**, todos presentes en el formulario reutilizado:

| Grupo | Campos backend |
|---|---|
| Identificación | internal_id, name, official_tag, electronic_tag |
| Clasificación | species_id, breed_id, gender_id, status_id |
| Ubicación | farm_id, lot_id |
| Nacimiento | birth_date, birth_weight |
| Filiación | mother_id, father_id |
| Observaciones | notes |

`is_active` es un dato de respuesta, no un campo editable de este formulario. No se agregaron fotografía, organización, ni campos ajenos al contrato.

## Botón, ruta y presentación

En el encabezado de la ficha, **Vista previa de edición** aparece junto a Editar animal, que continúa dentro de WriteOnly. La nueva ruta estática `/animals/:animalId/edit-preview` reutiliza ProtectedRoute y CurrentContextProvider. La página exige sesión, canRead y organización activa, valida UUID y respuesta con isAnimal, y usa clave por revisión de sesión/organización/animal. Las respuestas tardías se descartan si cambia el ámbito. El backend sigue imponiendo el alcance tenant de GET /api/animals/{animal_id}.

AnimalEditPreviewPage consulta únicamente ese animal y monta el mismo AnimalForm con `readOnly`. **Vista previa · Solo lectura** identifica la pantalla. El enlace Volver a la ficha conserva el animal seleccionado. El formulario se agrupa visualmente en seis secciones, con tarjetas blancas, controles claros, detalles esmeralda y una columna en móvil.

## Seguridad y comportamiento normal

- Todos los controles de la vista previa están dentro de un fieldset disabled; no hay botón Guardar ni acciones de eliminación.
- handleSubmit previene el evento y retorna inmediatamente en readOnly o DEMO, antes de crear payload o llamar a servicios mutantes. Se prueba también un submit programático.
- En vista previa no se consultan catálogos ni candidatos: se usan los valores y etiquetas del animal ya verificado. No se crean registros de catálogo ficticios. Las referencias de progenitores usan la información disponible o su UUID.
- La vista previa es de solo lectura también en modo normal y para OWNER. No autoriza edición a un rol de lectura.
- La edición normal conserva RequireWrite, catálogos, filtros dependientes, validaciones, payload y navegación existentes. Su prop readOnly permanece false por defecto. Se añadió un fieldset sin borde/margen/padding en modo normal para conservar la presentación y el comportamiento de los controles.
- El bloqueo global DEMO del cliente/proxy no se modifica. No hay nuevos endpoints, cambios JWT, credenciales o tokens en logs/URLs.
- La nueva pantalla realiza GET al animal; no inicia sesión ni envía POST, PUT, PATCH o DELETE. Las pruebas emplean mocks, sin bases persistentes.

## Archivos modificados

- frontend/src/animals/components/form/AnimalForm.tsx
- frontend/src/pages/AnimalDetailPage.tsx
- frontend/src/pages/AnimalDetailPage.css
- frontend/src/app/router.tsx
- frontend/src/animals/animal-detail.test.mjs

## Archivos creados

- frontend/src/pages/AnimalEditPreviewPage.tsx
- frontend/src/pages/AnimalEditPreviewPage.css
- frontend/src/animals/edit-preview.test.mjs
- docs/UI-ANIMAL-EDIT-PREVIEW-01.md

## Validación

Pruebas específicas iniciales: 18/18 PASS (12 del expediente y seis nuevas). Cubren los 15 valores precargados, etiquetas reales de opciones, ausencia de peticiones de catálogo, fieldset deshabilitado, ausencia de Guardar/Eliminar, cero servicios mutantes tras submit programático en ambos modos, edición normal con PUT y retorno a ficha, validación de finca/lote, consulta por animal, indicador y regreso, denegación por sesión/permisos, error de acceso a otro tenant, respuesta de otro animal, cambio de organización/sesión y reglas responsive/foco.

La prueba normal de edición usa servicios simulados para confirmar payload y navegación; no escribe datos reales. El rechazo de otra organización se comprueba con respuesta de acceso denegado simulada y los controles de alcance; no se afirma una nueva prueba HTTP contra datos persistentes.

Suite completa 864/864 PASS. Pruebas específicas repetidas tras la comprobación del botón: 18/18 PASS. Lint PASS. Build normal PASS. Build DEMO PASS.

Limitaciones: revisión visual manual pendiente; los controles deshabilitados no entran en el orden de tabulación, aunque conservan etiquetas y pueden recorrerse en modo lectura del lector de pantalla. El estado vacío del formulario es el propio valor vacío del registro, sin datos sustitutos. Los catálogos no se cargan en vista previa: esta muestra la instantánea real del animal, sin ofrecer opciones alternativas. No se cambiaron las siete secciones del expediente, login, Dashboard, permisos ni backend. Sin migraciones, seeds, grants o Git.
