# ADR-0001

## Arquitectura del Proyecto

Fecha:
2026

Estado:
Aceptado

---

Se decidió utilizar una arquitectura modular basada en aplicaciones Django.

Cada aplicación contiene:

- Models
- API
- Schemas
- Selectors
- Services

La lógica de negocio nunca deberá implementarse dentro de los endpoints.

Los endpoints únicamente:

- reciben solicitudes
- validan esquemas
- llaman servicios
- devuelven respuestas

Toda la lógica estará en Services.

Las consultas complejas estarán en Selectors.
