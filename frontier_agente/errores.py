"""Excepciones propias del agente: todas cuelgan de ErrorVNC."""


class ErrorVNC(Exception):
    """Fallo del cliente VNC/RFB; permite capturarlos a todos juntos."""


class ErrorConfiguracion(ErrorVNC):
    """Falta o está mal una variable de entorno u otro valor de configuración."""


class ErrorConexion(ErrorVNC):
    """No se pudo abrir, usar o mantener el WebSocket con el escritorio."""


class ErrorProtocolo(ErrorVNC):
    """El servidor habló algo distinto del RFB 3.8 que esperamos."""


class ErrorAutenticacion(ErrorVNC):
    """El servidor rechazó la contraseña (SecurityResult distinto de cero)."""


class ErrorTiempo(ErrorVNC):
    """Una lectura o un envío agotó su tope de tiempo."""
