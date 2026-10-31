"""
Configuración de pytest: pone agente/ en sys.path para poder importar
frontier_agente y arnes desde las pruebas.
"""
import sys
from pathlib import Path

AGENTE = Path(__file__).resolve().parents[1]
if str(AGENTE) not in sys.path:
    sys.path.insert(0, str(AGENTE))
