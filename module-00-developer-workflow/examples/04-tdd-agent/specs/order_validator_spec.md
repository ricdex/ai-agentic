# Spec: OrderValidator

Implementar una clase `OrderValidator` que valida si un Order puede hacer
una transición de estado.

## Comportamiento esperado

- `can_transition(current_status, new_status)`:
  - Retorna `True` si la transición es válida según las reglas de negocio
  - Retorna `False` si no es válida
  - Transiciones válidas: PENDING→CONFIRMED, CONFIRMED→SHIPPED, SHIPPED→DELIVERED
  - CANCELLED y DELIVERED son estados terminales (no puede salir de ahí)
  - Desde PENDING o CONFIRMED se puede ir a CANCELLED
  - No se puede saltar estados (PENDING→SHIPPED es inválido)

- `validate(current_status, new_status)`:
  - Si la transición es válida: no hace nada (retorna None)
  - Si es inválida: lanza `ValueError` con un mensaje que explique por qué
    (incluir el estado actual y el estado destino en el mensaje)

## Inputs

Los estados son strings: `"pending"`, `"confirmed"`, `"shipped"`, `"delivered"`, `"cancelled"`
