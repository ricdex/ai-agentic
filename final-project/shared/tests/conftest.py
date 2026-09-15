import os

# shared/claude_client.py y shared/github_client.py leen estas env vars al
# instanciar sus clientes. En CI y local no hay credenciales reales: los
# tests unitarios mockean las llamadas de red, así que un valor dummy alcanza.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("GITHUB_TOKEN", "test-token")
os.environ.setdefault("REDIS_HOST", "localhost")
