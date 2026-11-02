# D6C-2B.1 — Preparación; no autorización de ejecución

`prepare_demo_authorization --run-id <UUID D6B>` prepara exclusivamente almacenamiento
privado. Revalida original/copia/backup/recibo y exige copia fresh sin colisiones.
No abre SQLite para escritura, no migra, no emite grants ni crea usuarios.

El almacenamiento vive bajo `%LOCALAPPDATA%\AgroCore\DemoDataV1`:

- `keys/<run-id>/authorization.key`: 32 bytes aleatorios para HMAC.
- `keys/<run-id>/encryption.key`: 32 bytes aleatorios para cifrado Fernet.
- `keys/<run-id>/dataset-signing.key`: 32 bytes aleatorios para manifiestos.
- `authorizations/<run-id>/grants`: vacío; futuro grant firmado.
- `authorizations/<run-id>/ledger`: vacío; futuras evidencias nonce.used.
- `deliveries/<run-id>/D2`, `D3`, `D4`: vacíos; futuros bundles cifrados.

Las DACL se aplican antes de escribir material secreto: únicamente SID del
operador autorizado y SYSTEM. Nunca se muestran bytes de claves ni contraseñas.
Archivos exclusivos, fsync, claves distintas, sin sobrescritura ni rotación.
Un fallo deja evidencia parcial y obliga a detenerse; no existe reparación o
limpieza automática. Las claves existentes deben conservarse para recuperar el
mismo ciphertext. Perder la clave de cifrado impide recuperar credenciales;
no se regeneran contraseñas ni se adopta una fase sin manifiesto verificable.
No copiar claves a tickets, consola, logs o repositorio. Un respaldo de claves
requiere almacenamiento privado independiente y autorización específica.

## Procedimiento futuro de emisión (NO realizado en esta fase)

Exigir autorización humana independiente D6C-2B.2, revalidar receipt D6B,
identidades canónicas/volumen/file-id, hashes, SID, ACL, estado y exclusión de
escritores. El formato certificado está en D6C-2A.md y rehearsal_command.FIELDS.
Construir payload VERSION, run_id, nonce UUID nuevo, expires ahora+120 segundos
(máximo 300), mode execute, SID, identidades copy/original, SHA256 del recibo,
identidad del ledger y artifact_digest. Firmar canonical_json(payload) mediante
HMAC-SHA256 con authorization.key; publicar JSON exclusivo nonce.json solamente
en grants de ese run-id. No hay emisor operativo de grants en esta fase.

El ejecutor certificado rechaza alteraciones, destino distinto, expiración y
reutilización; consume nonce.used exclusivamente y de forma durable antes de
abrir el writer. Una reanudación exige NUEVO grant mode resume y grant consumido
anterior como procedencia, mismos bundles/claves y manifiestos válidos. No borrar
ledger ni grants usados. No autorizar otras bases ni la original. Una variable
de entorno únicamente selecciona settings/copias; nunca autoriza escritura.

Ejecutar dry-run después de preparar, comprobar ledger/grants/bundles vacíos,
ejecución sin grant rechazada y seed_demo_ranches --write bloqueado. Conservar
hashes e identidades originales y de ensayo. D2/D3/D4 mantienen commits por fase;
la preparación de archivos tampoco es una transacción global y una interrupción
real/pérdida eléctrica no queda certificada por fallos simulados.
