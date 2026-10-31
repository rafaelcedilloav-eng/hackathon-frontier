"""
Pruebas para `depurar_resumen` (Tabla R).
"""
import pytest
from frontier_agente.resumen import depurar_resumen


class TestDepurarResumen:
    """Tabla R: depurar_resumen(resumen: str, secretos: list[str]) -> str"""

    def test_R1_reemplaza_todas_apariciones(self):
        # R1: ("clave Zeta y otra vez Zeta", ["Zeta"]) -> "clave [oculto] y otra vez [oculto]"
        resultado = depurar_resumen("clave Zeta y otra vez Zeta", ["Zeta"])
        assert resultado == "clave [oculto] y otra vez [oculto]"

    def test_R2_sin_secretos_en_texto(self):
        # R2: ("sin nada", ["Zeta"]) -> "sin nada"
        resultado = depurar_resumen("sin nada", ["Zeta"])
        assert resultado == "sin nada"

    def test_R3_secreto_vacio_se_ignora(self):
        # R3: ("x", [""]) -> "x"
        resultado = depurar_resumen("x", [""])
        assert resultado == "x"

    def test_R4_lista_vacia(self):
        # R4: ("x", []) -> "x"
        resultado = depurar_resumen("x", [])
        assert resultado == "x"

    def test_R5_secretos_mas_largos_primero(self):
        # R5: ("claveclave2", ["clave", "clave2"]) -> "[oculto][oculto]"
        # Primero se reemplaza "clave2" (más largo), luego "clave"
        resultado = depurar_resumen("claveclave2", ["clave", "clave2"])
        assert resultado == "[oculto][oculto]"