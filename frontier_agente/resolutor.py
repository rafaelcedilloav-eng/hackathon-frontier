"""Decide a qué registro se refiere la tarea entre los candidatos que mostró la pantalla."""
from frontier_agente.texto import normalizar_clave, valores_iguales
from frontier_agente.tipos_agente import Candidato, Resolucion


def resolver(candidatos: list[Candidato], identificador: dict[str, str]) -> Resolucion:
    # NOTA: reglas en orden: quitar repetidos, contar, paso A por identificador,
    # paso B por pares; si nada distingue, ambiguo con todos. Nunca lanza:
    # lo que no es un Candidato se descarta, un identificador no hashable se
    # trata como str y un identificador que no es diccionario deja la
    # resolución en ambiguo.
    pares_de_la_tarea = identificador if isinstance(identificador, dict) else {}
    unicos = _quitar_repetidos(candidatos)
    if not unicos:
        return Resolucion(tipo="ninguno")
    if len(unicos) == 1:
        return Resolucion(tipo="uno", elegido=unicos[0])
    por_identificador = _coincidencias_por_identificador(unicos, pares_de_la_tarea)
    if len(por_identificador) == 1:
        return Resolucion(tipo="uno", elegido=por_identificador[0])
    filtrados = _filtrar_por_pares(unicos, pares_de_la_tarea)
    if len(filtrados) == 1:
        return Resolucion(tipo="uno", elegido=filtrados[0])
    return Resolucion(tipo="ambiguo", candidatos=tuple(unicos))


def _quitar_repetidos(candidatos: list[Candidato]) -> list[Candidato]:
    # NOTA: candidatos con el mismo identificador cuentan como uno; se conserva
    # el primero y se descarta cualquier cosa que no sea un Candidato. El
    # identificador se deduplica como str: uno no hashable (una lista) no revienta.
    unicos = []
    vistos = set()
    for candidato in candidatos:
        if not isinstance(candidato, Candidato):
            continue
        clave = str(candidato.identificador)
        if clave not in vistos:
            vistos.add(clave)
            unicos.append(candidato)
    return unicos


def _coincidencias_por_identificador(
    candidatos: list[Candidato], identificador: dict[str, str]
) -> list[Candidato]:
    # NOTA: paso A: candidatos cuyo identificador coincide con algún valor de la tarea;
    # valores_iguales convierte a texto cualquier valor raro antes de comparar.
    valores_de_la_tarea = list(identificador.values())
    return [
        candidato
        for candidato in candidatos
        if any(valores_iguales(valor, candidato.identificador) for valor in valores_de_la_tarea)
    ]


def _filtrar_por_pares(
    candidatos: list[Candidato], identificador: dict[str, str]
) -> list[Candidato]:
    # NOTA: paso B: el candidato debe coincidir en cada par (llave, valor) de la tarea;
    # las llaves no textuales se normalizan igual (normalizar_clave las convierte).
    pares = [(normalizar_clave(llave), valor) for llave, valor in identificador.items()]
    return [
        candidato
        for candidato in candidatos
        if all(_coincide_en_par(candidato, llave, valor) for llave, valor in pares)
    ]


def _coincide_en_par(candidato: Candidato, llave: str, valor: object) -> bool:
    # NOTA: la llave se compara normalizada; una llave que el candidato no
    # expone no lo descarta, pero si la expone el valor debe ser igual.
    # Si dos llaves del candidato normalizan igual, gana la primera que
    # aparece en sus campos (mismo criterio que los repetidos: se conserva
    # la primera) y la última no la sobreescribe.
    campos_normalizados: dict[str, object] = {}
    for nombre, valor_campo in candidato.campos.items():
        campos_normalizados.setdefault(normalizar_clave(nombre), valor_campo)
    if llave not in campos_normalizados:
        return True
    return valores_iguales(valor, campos_normalizados[llave])
