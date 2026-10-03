import sys
from pathlib import Path

# Los ejemplos son scripts sueltos, no un paquete: exponerlos para importarlos.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
