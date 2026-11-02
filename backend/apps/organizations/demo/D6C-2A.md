# D6C-2A — comando controlado, sin ejecución persistente en esta fase

Punto de entrada: `seed_demo_rehearsal`. El comando normal
`seed_demo_ranches --write` sigue rechazado. No existe emisor de grants reales,
provisionador automático de claves ni bandera booleana que habilite escrituras.

## Consulta sin escrituras

`manage.py seed_demo_rehearsal --run-id <UUID> --settings=config.settings.local`
es dry-run por defecto: valida D6B, identidad, migraciones ya aplicadas,
catálogos y colisiones; no crea directorios, claves, credenciales o nonce usado.
Producción y settings desconocidos se rechazan. Para inspeccionar fases ya
ejecutadas, añadir `--reference-authorization <grant-consumido.json>`; requiere
las mismas claves y evidencia durable, pero no consume ni reautoriza el grant.
La lectura de inventarios usa una conexión SQLite físicamente `mode=ro`.

## Ejecución futura — requiere autorización independiente D6C-2B

Settings exclusivos: `config.settings.demo_rehearsal_execution`. El run-id se
selecciona con `AGROCORE_DEMO_REHEARSAL_RUN_ID`; **solo selecciona una copia
para lectura, no concede permiso**. Globalmente default sigue siendo `mode=ro`.
El comando necesita `--execute --run-id <UUID> --authorization-file <grant>`.
Local, producción y el viejo `demo_rehearsal_write` no pueden activar el flujo.
No hay argumento para recibir una base arbitraria o cambiar la original.

El grant JSON debe existir con ACL privada, filename `<nonce-UUID>.json`, en
`LocalAppData/AgroCore/DemoDataV1/authorizations/<run>/grants/`.
Formato: `{payload, signature}`; signature es HMAC-SHA256 del JSON canónico
ordenado UTF-8 (misma canonical_json de D1). Payload tiene exactamente:
`version=D6C-2A-v1`, `run_id`, `nonce`, `expires` (epoch finito, hasta 300 s),
`mode=execute|resume`, `sid`, identidades `copy` y `original` (path/device/file_id),
`receipt` (SHA256 D6B), `ledger` (path/device/file_id) y `artifacts` (digest del
plan fijo de claves, grants, ledger y entregas). No se aceptan campos JSON
duplicados, firmas alteradas, SID distinto ni otros destinos/run/recibos.

Claves separadas: `.../keys/<run>/authorization.key`, `encryption.key` y
`dataset-signing.key`, 32 bytes aleatorios distintos cada una. El código solo
lee archivos ya provisionados; jamás los genera ni imprime. Ledger privado:
`.../authorizations/<run>/ledger/`. D6C-2B debe autorizar y provisionar estas
ubicaciones con SID Windows autorizado y SYSTEM únicamente, antes de emitir
el grant. Esto NO se hizo en D6C-2A.

Tras verificar preflight y fases, se crea exclusivamente `<nonce>.used` con
hash del payload, fsync y ACL verificada. Un fallo consume el nonce igualmente.
El permiso se entrega una sola vez a una sesión del proceso/hilo y se revoca
al salir. El guard adicional D2 no acepta variables de entorno, callbacks ni
tokens sin evidencia: revisa conexión, HMAC, marcador, archivos, identidades,
claves, recibo y ACL. El guard legacy queda intacto fuera de esa sesión.

La conexión de escritura existe solo en el hilo del comando; al terminar se
restaura su wrapper anterior y no se altera DATABASES ni el destino normal.
El original se mantiene abierto con denegación Windows de escritura/borrado.
La copia queda fijada contra sustitución y SQLite mantiene bloqueo EXCLUSIVE
entre los commits. WAL/SHM/journal inesperados y escritores activos provocan
rechazo; nunca se ejecutan checkpoints ni migraciones.

## Entrega y recuperación

Bundles y manifiestos cifrados: `.../deliveries/<run>/D2,D3,D4/`. ACL privada
antes de escribir, creación exclusiva, pending y publicación sin sobrescritura.
El cifrado autenticado conserva la estrategia Fernet D2. Claves nunca se
incorporan al bundle ni se guardan en el mismo directorio de entrega.

D2, D3 y D4 hacen **commits separados**, no una transacción única. Una fase
fallida se revierte; las anteriores se conservan. La preinspección verifica
firmas, cadena de padres, inventarios, catálogos, filas originales y registros
añadidos que no pertenezcan al dataset. Detecta publicación pendiente, fases
completas, ausencia de padres y residuos no confirmados; no borra ni adopta.

Reanudar exige `--execute --resume --authorization-file <nuevo-grant-resume>
--reference-authorization <grant-consumido>` y las mismas tres claves. El grant
anterior solo fija procedencia; un nonce nuevo autoriza el intento. Los pending
compatibles se verifican y publican con el **mismo ciphertext**, sin regenerar
contraseñas. Si el bundle quedó antes de un rollback y no coincide con la base,
se detiene para investigación; no hay reset/clean/force/update-existing.

## Alcance de certificación

Pruebas de integración usan referencias D6B sintéticas, SQLite descartable,
grants y claves efímeros. No se emitieron grants reales ni se sembró la copia
persistente. D6C-2B requiere consentimiento separado, validación de rutas/ACL,
provisión segura, nueva comprobación de escritores/espacio y emisión de un
grant de corta vigencia justo antes de ejecutar. No se certifican cortes
eléctricos, pérdida física del disco ni compromiso del SID autorizado.
