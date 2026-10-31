"""Juez: compara lo que se pidió con lo que se releyó de la pantalla."""
from frontier_agente.texto import normalizar_clave, valores_iguales
from frontier_agente.tipos_agente import Diferencia

# NOTA: lo que no se pudo leer se reporta como vacío, nunca como None.
VALOR_VACIO = ""
# NOTA: un esperado que no es dict no permite enumerar campos; se reporta con
# este nombre de campo y su repr recortado, nunca como falso verde.
CAMPO_ESPERADO_RARO = "(esperado)"
MAX_CARACTERES_REPR = 40
SUFIPO_TRUNCADO = "..."


def comparar_campos(
    esperado: dict[str, str], leido: object, exentos: tuple = ()
) -> list[Diferencia]:
    # NOTA: solo se miran los campos esperados, en su orden; las llaves de
    # exentos no se comparan ni se devuelven (tabla J2: no hay con qué
    # verificarlas contra la tarea, y así nunca dan un falso rojo); las llaves
    # extra de lo leído se ignoran y una lista vacía significa que coincide
    # todo. Una lectura que no es dict o viene vacía nunca da [] si había algo
    # esperado (J8); un esperado que no es dict tampoco: da [] solo si está vacío.
    if not isinstance(esperado, dict):
        return [Diferencia(CAMPO_ESPERADO_RARO, _repr_corto(esperado), VALOR_VACIO)]
    if not esperado:
        return []
    lectura = leido if isinstance(leido, dict) else {}
    diferencias = []
    for campo, valor_esperado in esperado.items():
        if _es_exento(campo, exentos):
            continue
        valor_leido = lectura.get(campo)
        if valor_leido is None or str(valor_leido).strip() == VALOR_VACIO:
            diferencias.append(Diferencia(campo, valor_esperado, VALOR_VACIO))
        elif not valores_iguales(valor_esperado, valor_leido):
            diferencias.append(Diferencia(campo, valor_esperado, valor_leido))
    return diferencias


def _es_exento(campo: str, exentos: tuple) -> bool:
    # NOTA: exento por llave exacta o igual sin acentos (normalizar_clave),
    # para que el exento que declaró el intérprete coincida aunque la llave
    # venga escrita con acentos o mayúsculas.
    if campo in exentos:
        return True
    return any(
        normalizar_clave(campo) == normalizar_clave(exento) for exento in exentos
    )


def _repr_corto(valor: object) -> str:
    # NOTA: repr recortado para no arrastrar objetos enormes dentro de una Diferencia.
    texto = repr(valor)
    if len(texto) > MAX_CARACTERES_REPR:
        return texto[:MAX_CARACTERES_REPR] + SUFIPO_TRUNCADO
    return texto
