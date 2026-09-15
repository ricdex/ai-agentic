# Desarrollo local

## Requisitos

- Python 3.11 o superior para los ejemplos.
- Docker y Docker Compose solo para el proyecto final.
- `ANTHROPIC_API_KEY` únicamente para demos que llaman a un modelo real.

## Ejecutar un ejemplo

Instala las dependencias indicadas en el README del módulo y ejecuta el archivo dentro de su carpeta `examples/`.

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
python examples/01_hello_agent.py
```

Antes de implementar una nueva capacidad, crea una spec desde `module-00-developer-workflow/templates/feature-spec.md.template`. Ejecuta los tests y evals descritos en esa spec; no declares una capacidad terminada solo porque el agente produjo código.

## Proyecto final

El proyecto final requiere Docker, GitHub y credenciales reales. Consulta `final-project/README.md` para su configuración. No uses secretos de producción en local.

### Tests y cobertura

`final-project/shared/` (los clientes de Claude, GitHub, cola y los modelos que usan vm1/vm2/vm3) tiene su propia suite de tests unitarios, sin mocks de red reales:

```bash
cd final-project
pip install -r vm1-orchestrator/requirements.txt ruff pytest pytest-cov
make lint    # ruff check shared/
make test    # pytest + cobertura; falla si baja de 80% (pyproject.toml)
```

CI (`.github/workflows/ci.yml`) corre lo mismo en cada push/PR, además de un chequeo de sintaxis sobre los `examples/` de todos los módulos (no ejecuta las llamadas reales a Claude, solo detecta código roto).
