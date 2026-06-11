# CLAUDE.md — E-Commerce Core

## Stack

- Runtime: Python 3.11, FastAPI, PostgreSQL
- Tests: pytest, fixtures en `conftest.py`
- Linting: ruff (no black, no flake8)
- Type hints: siempre, sin `Any` salvo comentario justificado

## Convenciones de código

- Los domain objects retornan valores o lanzan `ValueError` — sin códigos de error numéricos
- Los casos de uso (services) retornan `Result[T, DomainError]` — nunca propagan excepciones crudas
- Tests unitarios en `tests/unit/`, tests de integración en `tests/integration/`
- Nombres en inglés, comentarios en español
- Un archivo por clase de dominio (no agrupar varias entidades en un archivo)

## Workflow de desarrollo

- Siempre correr `pytest tests/unit/` antes de cualquier commit
- Coverage mínimo: 80% — CI falla si baja
- El mensaje de commit explica el "por qué", no el "qué"

## Qué evitar

- No usar variables de módulo como estado
- No commitear archivos `.env`
- No agregar dependencias sin actualizar `requirements.txt` y justificar en el PR
- No usar `print()` en código de producción — usar `logging` estructurado
