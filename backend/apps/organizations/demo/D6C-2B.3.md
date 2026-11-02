# D6C-2B.3 — Emisor operativo independiente

El emisor `issue_demo_rehearsal_grant` publica exclusivamente un grant HMAC
compatible con rehearsal_command._Authority; nunca abre SQLite para escritura
ni invoca el seeder. No se emiten grants persistentes durante la certificación.
La descripción histórica de D6C-2A/D6C-2B.1 sobre ausencia de emisor corresponde
a esas fases; este componente lo proporciona para una futura autorización.

Tras autorización humana independiente para D6C-2B.2:

```
python manage.py issue_demo_rehearsal_grant --settings=config.settings.demo_rehearsal_execution --run-id <run-id> --confirm-run-id <mismo-run-id>
```

El entorno identifica el run-id de los settings dedicados. No es autorización
booleana ni se admite una ruta SQLite arbitraria. Para recuperación se exige
`--reference-authorization <grant previamente consumido>`; el emisor valida su
firma y ledger, y emite mode resume, nunca adopta fases desconocidas.

Reutiliza claves D6C-2B.1 sin crearlas/rotarlas. Exige ACL SID actual autorizado
y SYSTEM, referencias D6B y snapshots protegidos, migraciones conocidas,
catálogos y colisiones; copia fresh para execute, fases válidas para resume.
Payload exacto VERSION/FIELDS: run-id, SID, nonce UUIDv4 generado por el SO,
original/copia path-volume-file-id, hash del recibo, identidad del ledger,
digest de rutas de artefactos y expiración. Predeterminada 120 segundos,
permitida 1..120. Firma HMAC-SHA256 canonical_json con authorization.key.

Usa el mismo mutex por recibo que ejecución/provisión, con rechazo inmediato
de concurrencia. Original y copia están abiertos con exclusión Windows de
escritores y sustituciones durante emisión. Revalida referencias, claves,
ledger y expiración justo antes de publicar. No modifica guards existentes.

Escribe nonce.pending exclusivo bajo ACL privadas, flush/fsync, renombra
atómicamente en el mismo directorio a nonce.json sin sobrescribir (Windows).
La salida contiene únicamente la ubicación, nunca token, firma o claves.
No elimina evidencia ante fallos. Pending, grants no consumidos, ledger
desconocido o incompleto bloquean nuevas emisiones. Incluso un grant caducado
no se reemplaza automáticamente: requiere inspección independiente.

El consumidor existente conserva consumo exclusivo durable nonce.used y
rechazo de reutilización. Un fallo de ledger bloquea reintento con ese nonce;
no se trata la ausencia de ejecución como permiso para borrar su evidencia.
No se emite ni consume automáticamente al hacer dry-run o ejecutar el seeder.
`seed_demo_ranches --write` sigue bloqueado.

Publicación atómica no implica durabilidad absoluta ante pérdida eléctrica.
Si hay fallo tras rename, el grant puede existir: conservarlo e inspeccionar,
no reemitir. La preparación, emisión y D2/D3/D4 no forman una transacción global.
La certificación usa solo SQLite y directorios temporales; no certifica una
interrupción eléctrica real ni la custodia frente a un SID autorizado comprometido.
