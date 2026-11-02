# D7C — Visor local de credenciales DEMO

El visor permite seleccionar una sola cuenta del run `93f864fe-0e45-4eaa-9253-79f8f7f88467`, revelar temporalmente su contraseña o copiarla con confirmación. No inicia sesión, no recibe ni transfiere JWT y no abre puertos. No cambia frontend, autenticación, settings ni formatos criptográficos.

## Abrir manualmente (no ejecutado con credenciales reales durante D7C)

Desde PowerShell con la misma identidad Windows autorizada por las ACL D6B, sin administrador:

```powershell
Set-Location C:\programas\Proyectos\agrocore-platform
& .\backend\Open-DemoCredentials.ps1
```

El launcher usa `.venv\Scripts\pythonw.exe -B` y una ventana oculta de proceso; los secretos no pasan por argumentos, stdout, stderr, archivos temporales ni logs. El visor muestra su propia ventana gráfica. Si falla una comprobación no se habilita ningún selector; se presenta un error genérico. Si Tcl/Tk o pythonw no están disponibles, el visor no puede abrirse. No instalar dependencias ni cambiar ACL para eludir rechazos.

1. Esperar la validación completa; puede tardar porque verifica los inventarios D2/D3/D4.
2. Seleccionar **Rancho El Encino Demo**.
3. Seleccionar la cuenta marcada **OWNER** en el selector de usuario/rol.
4. Copiar el correo desde el campo de solo lectura con Ctrl+C. Pulsar **Copiar contraseña (30 s)** y confirmar.
5. Pegar en el formulario normal `http://127.0.0.1:5174/login` y enviarlo. El backend DEMO y frontend DEMO deben estar iniciados por los launchers D7A/D7B; este visor no los inicia.
6. Cerrar el visor. No guardar la contraseña en el administrador de contraseñas del navegador.

## Orden de validación autorizado

- Settings exclusivamente `config.settings.demo_view`. Rutas, identidades de archivo, run fijo y hashes mediante `verified_locations`; exclusión de escritores de original y copia mediante `frozen_source`, mantenida durante la vida del visor. Solo comprueba migraciones existentes; no las aplica.
- `_Authority`, `_binding` y evidencia de consumo existente verifican ACL privadas, claves separadas, firma de procedencia, SID actual, run-id y ledger. No se emite ni consume ningún grant nuevo. Se exige exactamente un grant y un registro de ledger. Los directorios de entrega deben contener únicamente su bundle final.
- Antes del descifrado se comprueban árboles privados, archivos canónicos y hashes de los artefactos. `_phase_status` usa `_read_bundle` para autenticar y descifrar en memoria, con el mismo Fernet existente.
- `_phase_status` verifica recibos firmados, cadena D2/D3/D4, inventarios, filas de referencia, ausencia de cuentas ajenas y correspondencia de contraseñas con los hashes mediante funciones certificadas y SQLite `mode=ro`.
- Solo con todas las fases completas se lee D2 con `_read_bundle` para construir el selector; se comprueba que el ciphertext y demás artefactos conservan los mismos hashes que durante la validación y que las claves conservan identidad. La selección exige 30 usuarios únicos en cinco organizaciones. Los nombres se consultan únicamente sobre los UUID del inventario firmado, con conexión de solo lectura.
- Ninguna cuenta se entrega a la interfaz antes de terminar lo anterior. No hay opción de ruta, run alternativo, exportación masiva o cuenta real preexistente.

## Ventana y portapapeles

Contraseña vacía/oculta por defecto. Seleccionar otra organización o usuario la oculta. Mostrar y copiar requieren confirmaciones separadas. La revelación se oculta a los 30 segundos; también al perder foco de la ventana. Se bloquea la copia directa del campo de contraseña para que la acción pase por confirmación.

El botón de copia coloca únicamente la contraseña seleccionada. A los 30 segundos y al cerrar, la herramienta compara el valor actual con su última copia y solo lo limpia si sigue coincidiendo. Las tareas antiguas no borran una copia más reciente. No se mantiene historial.

Otros procesos locales pueden leer el portapapeles mientras contiene la contraseña. El historial o sincronización del portapapeles de Windows, administradores externos y capturas de pantalla pueden conservarla fuera del control del visor; desactivar esas funciones antes de copiar. No se promete borrado criptográfico de memoria, portapapeles, pagefile o volcados del sistema. La herramienta descarta referencias y limpia controles cuando es posible. Una indisponibilidad del portapapeles puede impedir su limpieza; no se promete exclusión de otros procesos ni operación atómica global entre lectura y limpieza.

## Pruebas

Los tests nuevos viven en `apps.organizations.tests_demo_credential_viewer`. Usan cuentas ficticias, claves/bundles y SQLite temporales; no ejecutan el entry point contra archivos persistentes. Incluyen pruebas del controlador, ventana Tk con cuenta ficticia, rechazo de run erróneo antes del descifrado, ACL rechazadas, ciphertext alterado, firma de recibo inválida, fases incompletas, selección y confirmación, temporizadores de copia, preservación del contenido posterior del usuario, cierre y ausencia de archivos nuevos o secretos en texto plano durante la consulta validada.

```powershell
& .\.venv\Scripts\python.exe -B .\backend\manage.py test apps.organizations.tests_demo_credential_viewer --settings=config.settings.demo_d2_testing --noinput
& .\.venv\Scripts\python.exe -B .\backend\manage.py check --settings=config.settings.demo_view
```

Las pruebas requieren la instalación local Tcl/Tk y acceso al escritorio Windows. En el sandbox, importar tkinter funciona pero crear Tk puede fallar por acceso a init.tcl; la prueba de ventana con datos ficticios pasó con ejecución autorizada fuera del sandbox. No se cambió Tcl ni sus permisos.

Los resultados finales y hashes se registran al finalizar la validación. No se ha abierto el visor con credenciales reales.

## Reporte final

**Decisión: READY para el primer uso manual autorizado.** El visor no se ejecutó con credenciales reales; no se afirma una validación visual del dataset persistente.

| Campo | Resultado |
|---|---|
| Archivos creados | backend/Open-DemoCredentials.ps1; backend/open_demo_credentials.py; backend/apps/organizations/demo/credential_viewer.py; backend/apps/organizations/tests_demo_credential_viewer.py; docs/D7C.md |
| Archivos existentes modificados | Ninguno |
| Launcher PowerShell | Sintaxis PASS; usa pythonw del entorno local, sin administrador, sin secretos en argumentos |
| Interfaz | Tkinter disponible; prueba real de ventana con cuenta ficticia PASS |
| Validación | Ruta fija, hashes D7A, SID del grant consumido y ACL privadas; funciones certificadas para descifrado autenticado y recibos/manifiestos/inventarios D2/D3/D4; SQLite mode=ro; selección bloqueada hasta completar todo |
| Protección de credenciales | Sin endpoints, exportación masiva, login automático, JWT, stdout o archivos descifrados; errores GUI genéricos; referencias descartadas al cerrar |
| Portapapeles | Confirmación; copia individual; limpieza condicional a 30 segundos y cierre; preserva contenido posterior distinto |
| Pruebas D7C finales | 11/11 PASS en 154.563 s con ejecución autorizada para Tcl/Tk; datos y bases temporales |
| Regresión backend | 56/56 PASS en 473.499 s: primera versión de 9 pruebas D7C, tests_demo_view, tests_demo_authorization_storage y tests_demo_rehearsal_command. Las 11 pruebas finales D7C se ejecutaron después, incluyendo GUI y recibo firmado inválido |
| Django check | PASS con config.settings.demo_view: 0 incidencias |
| Comprobaciones estáticas | Sintaxis Python y parser PowerShell PASS; no se añadieron dependencias |
| Configuración normal | Sin cambios a frontend, settings, modelos, servicios ni flujo JWT |
| Operaciones persistentes | Sin migraciones, seeds, nuevos grants, cambios de claves/usuarios/contraseñas, ni uso de Git |

Hashes SHA256 comprobados antes y después, sin cambios:

- Original: `7726ad14f1d855cfc0ee9a2a0a8c2039c4cc84b2e885b7f0cbc78317f9d0f2a0`
- Copia DEMO: `aa4a77d2e9cdf8f8e72fafa42efb7ff2bdc2bae79efdd4f916f68872eeaebd2e`

Limitaciones: un cierre forzado puede impedir la limpieza; procesos locales, historial de portapapeles o mecanismos del sistema pueden conservar secretos. No hay garantía de borrado criptográfico. La exclusión de escritores de ambas bases se mantiene mientras el visor esté abierto. La primera ejecución con el dataset real queda pendiente de la decisión manual del usuario, conforme al alcance autorizado.
