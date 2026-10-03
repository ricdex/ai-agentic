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

### Tests de los ejemplos de módulos

Algunos ejemplos separan la lógica pura (patrones de agente, context engineering, retrieval, guardrails) de las llamadas a Claude, y tienen tests unitarios que corren **sin red ni API key** usando LLMs y clientes falsos:

| Ejemplo | Tests |
|---|---|
| `module-02-workflow-design/examples/agent_patterns.py` | `module-02-workflow-design/tests/` |
| `module-03-dev-workflows/examples/context_manager.py` | `module-03-dev-workflows/tests/` |
| `module-05-production/examples/guardrails.py` | `module-05-production/tests/` |
| `module-06-rag-memory/examples/05_advanced_retrieval.py`, `06_agentic_rag.py` | `module-06-rag-memory/tests/` |

Desde la raíz del repo:

```bash
pip install anthropic pytest pytest-cov
pytest                                      # todos (config en pytest.ini)
pytest --cov --cov-report=term-missing      # + cobertura; falla si baja de 80% (.coveragerc)
pytest module-06-rag-memory/tests -q        # un módulo
```

Al agregar tests para otro ejemplo: sumá su carpeta `tests/` a `testpaths` en `pytest.ini` y el archivo a `include` en `.coveragerc`.

### Troubleshooting

- `ModuleNotFoundError` al importar un ejemplo desde un test: cada `tests/conftest.py` agrega su `examples/` al `sys.path`. Los archivos que empiezan con número se importan con `importlib.import_module("05_advanced_retrieval")`.
- `import file mismatch` entre módulos: `pytest.ini` usa `--import-mode=importlib`; no lo quites.

