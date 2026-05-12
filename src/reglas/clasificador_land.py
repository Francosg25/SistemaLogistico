"""
Clasificador de BUs especiales para LAND.

REGLA (de REGLAS_PROCESO líneas 79-81):
    🔴 Items con 'Machine' o maquinaria → BU = Machine
    🔴 Items sin BU identificable (TAPA, CHAROLA, etc.) → BU = Miscelaneus

Este módulo es un ASESOR: sugiere clasificaciones pero NO sobrescribe
automáticamente el BU que viene del reporte (a menos que esté vacío).
"""
import re
from typing import Optional
from src.utils.logger import configurar_logger

logger = configurar_logger("clasificador_land")


# ============================================================
# PATRONES DE CLASIFICACIÓN
# ============================================================
# Palabras clave que indican maquinaria
PATRONES_MACHINE = [
    r"\bmachine\b",
    r"\bmaquinaria\b",
    r"\bequipo\b",
    r"\binstrumento\b",
    r"\bherramienta\b",
]

# Palabras clave que indican items misceláneos sin BU claro
PATRONES_MISCELANEUS = [
    r"\btapa\b",
    r"\bcharola\b",
    r"\bpallet\b",
    r"\bembalaje\b",
    r"\betiqueta\b",
    r"\bmaterial\s+empaque\b",
]


def es_item_machine(descripcion: str) -> bool:
    """Determina si una descripción corresponde a un item Machine."""
    if not descripcion or not isinstance(descripcion, str):
        return False
    
    texto = descripcion.lower()
    return any(re.search(patron, texto, re.IGNORECASE) for patron in PATRONES_MACHINE)


def es_item_miscelaneus(descripcion: str) -> bool:
    """Determina si una descripción corresponde a un item Miscelaneus."""
    if not descripcion or not isinstance(descripcion, str):
        return False
    
    texto = descripcion.lower()
    return any(re.search(patron, texto, re.IGNORECASE) for patron in PATRONES_MISCELANEUS)


def clasificar_bu_land(
    bu_actual: Optional[str],
    descripcion: str = "",
    no_parte: str = "",
    forzar_clasificacion: bool = False,
) -> str:
    """
    Sugiere un BU para un item de Land según las reglas especiales.
    
    Args:
        bu_actual: BU que viene en el reporte (puede ser None o vacío)
        descripcion: Descripción del item
        no_parte: Número de parte del proveedor
        forzar_clasificacion: Si True, reemplaza el BU actual aunque exista
    
    Returns:
        BU sugerido (puede ser el original, 'Machine' o 'Miscelaneus')
    
    Reglas aplicadas:
        1. Si bu_actual existe y NO se fuerza → conservar
        2. Si descripción contiene 'Machine' → 'Machine'
        3. Si descripción contiene 'Tapa', 'Charola' → 'Miscelaneus'
        4. Si nada coincide → 'Miscelaneus' (default para sin clasificar)
    """
    # Regla 1: Respetar el BU del reporte si existe
    bu_limpio = (bu_actual or "").strip()
    if bu_limpio and not forzar_clasificacion:
        return bu_limpio
    
    # Texto combinado para análisis
    texto_completo = f"{descripcion} {no_parte}".strip()
    
    # Regla 2: Detección de Machine
    if es_item_machine(texto_completo):
        logger.debug(f"Clasificado como Machine: '{texto_completo[:50]}...'")
        return "Machine"
    
    # Regla 3: Detección de Miscelaneus
    if es_item_miscelaneus(texto_completo):
        logger.debug(f"Clasificado como Miscelaneus: '{texto_completo[:50]}...'")
        return "Miscelaneus"
    
    # Regla 4: Default
    logger.debug(f"Sin clasificación clara, asignado a Miscelaneus: '{texto_completo[:50]}...'")
    return "Miscelaneus"