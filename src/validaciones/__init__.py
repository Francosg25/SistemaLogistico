"""
Módulo de validaciones automáticas.
"""
from src.validaciones.validador import validar_todo, validar_operacion
from src.validaciones.reporte_validacion import (
    ReporteValidacion,
    Hallazgo,
    Severidad,
)

__all__ = [
    "validar_todo",
    "validar_operacion",
    "ReporteValidacion",
    "Hallazgo",
    "Severidad",
]