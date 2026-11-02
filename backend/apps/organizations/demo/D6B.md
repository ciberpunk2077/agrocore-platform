# D6B — respaldo y ensayo sin seeding

`prepare_demo_rehearsal --settings=config.settings.local --run-id <UUID>`
abre exclusivamente la base original configurada, en modo lectura, y emplea
`Connection.backup()` dos veces. No ejecuta migraciones, servicios ganaderos,
el seeder ni generación de credenciales. El comando rechaza otros settings.

Destino: LocalAppData real de Windows, `AgroCore/DemoDataV1/backups/<UUID>` y
`rehearsals/<UUID>`. DACL privada: SID del proceso y SYSTEM únicamente.
Los directorios existentes deben tener ya esa ACL; no se reparan permisos.
Se rechazan redirecciones de LOCALAPPDATA, junctions, symlinks, hardlinks,
destinos existentes, UUID reutilizados y espacio inferior a 4 veces el origen
más 64 MiB. Se deniegan handles concurrentes de escritura/borrado, WAL, SHM
y journal, sin cerrar procesos ni ejecutar checkpoints.

La validación compara esquema y conteos/hashes de **todas** las tablas con
el origen consistente, incluidas organizaciones, usuarios, memberships,
registros ganaderos y migraciones. No registra filas ni secretos. Comprueba
integridad, foreign keys, migraciones aplicadas y preflight exacto BOV/HOL,
SCALE, NAT, MILK/L y UUID protegido. La identidad de Rancho El Roble se
conserva al igual que todos los demás registros preexistentes.

`receipt.json` se publica al final. Un error deja artefactos sin autorización;
no se borran, adoptan ni sobrescriben automáticamente. Usar un nuevo UUID
después de investigar. El recibo contiene hashes, no una firma criptográfica:
depende de la ACL y no protege contra compromiso de la identidad autorizada.
No se certifican cortes eléctricos ni fallos de almacenamiento reales.

Para revisar la copia: definir `AGROCORE_DEMO_REHEARSAL_RUN_ID=<UUID>` y usar
`--settings=config.settings.demo_rehearsal`. Falta de recibo, hashes distintos,
datos alterados o referencia a la original impiden cargar esos settings.
SQLite se abre mediante URI `mode=ro`; tampoco el ORM puede escribir.
`seed_demo_ranches --dry-run` solamente inspecciona la copia y `--write`
continúa rechazado aun con AGROCORE_ENABLE_DEMO_WRITES=1. La configuración
local normal sigue apuntando a la original. No iniciar el servidor para
pruebas que requieran escrituras de sesiones con estos settings.

D6C requiere autorización humana nueva, un diseño separado de escrituras y
pruebas de recuperación; D6B no habilita D2-D5 fuera de SQLite desechable.
Nunca restaurar encima de la original. Conservar copia y backup en ubicaciones
distintas de la original; este respaldo local no sustituye un respaldo externo
ante pérdida física del disco. No generar credenciales demo en esta fase.
