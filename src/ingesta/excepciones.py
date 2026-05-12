"""
Excepciones personalizadas del módulo de ingesta.
Permiten manejar errores de forma específica y mostrar mensajes claros al usuario.
"""


class IngestaError(Exception):
    """Excepción base para todos los errores de ingesta."""
    pass


class ArchivoInvalidoError(IngestaError):
    """Se lanza cuando el archivo no es un Excel válido o está corrupto."""
    pass


class HojaNoEncontradaError(IngestaError):
    """Se lanza cuando no se encuentra la hoja esperada en el Excel."""
    def __init__(self, hoja_esperada: str, hojas_disponibles: list):
        self.hoja_esperada = hoja_esperada
        self.hojas_disponibles = hojas_disponibles
        super().__init__(
            f"No se encontró la hoja '{hoja_esperada}'. "
            f"Hojas disponibles: {hojas_disponibles}"
        )


class ColumnaFaltanteError(IngestaError):
    """Se lanza cuando faltan columnas obligatorias."""
    def __init__(self, columnas_faltantes: list, tipo_operacion: str):
        self.columnas_faltantes = columnas_faltantes
        self.tipo_operacion = tipo_operacion
        super().__init__(
            f"Faltan columnas obligatorias en {tipo_operacion}: "
            f"{', '.join(columnas_faltantes)}"
        )


class DatosVaciosError(IngestaError):
    """Se lanza cuando el archivo no contiene datos después del encabezado."""
    pass