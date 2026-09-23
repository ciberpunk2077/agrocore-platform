# Animals

## Objetivo

Administrar los animales registrados por una organización.

---

## Entidades relacionadas

Organization

↓

Farm

↓

Lot

↓

Animal

↓

Weights

↓

Health

↓

Vaccination

↓

Reproduction

---

## Reglas

- El Animal pertenece a una Organización.
- El Animal pertenece a un Farm.
- El Animal pertenece a un Lot.
- El Lot debe pertenecer al Farm.
- El Farm debe pertenecer a la Organización.
- La Breed debe pertenecer a la Species.
- La Madre debe ser hembra.
- El Padre debe ser macho.
