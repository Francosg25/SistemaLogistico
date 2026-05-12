"""
Módulo de inferencia de Business Units (BU) desde el patrón del Reference.

REGLA DE NEGOCIO:
    El Reference tiene formato: PREFIJO-X-####XX##.BU1[/BU2[/BU3...]]
    
    Ejemplos:
        FG-R-2202LE26.M19              → BU = M19   (único BU)
        FG-R-2208LE26.M46/M45          → BU = M45   (segundo BU)
        FG-R-2212LE26.M01/M45          → BU = M45   (segundo BU)
        FG-R-2214LE26.M01/M45/M23      → BU = M45   (segundo BU)

REGLA: Si hay múltiples BU separados por '/', tomar SIEMPRE el SEGUNDO.
       Si hay solo uno, tomar ese.
"""
import re
from typing import Optional, List
from src.utils.logger import configurar_logger

logger = configurar_logger("inferencia_bu")


# ============================================================
# PATRÓN REGEX PARA EXTRAER BU DEL REFERENCE
# ============================================================
# Captura todo lo que está después del último punto '.'
# Ejemplo: 'FG-R-2208LE26.M46/M45' → captura 'M46/M45'
PATRON_BU_REFERENCE = re.compile(r"\.([A-Za-z0-9/]+)\s*$")


def inferir_bu_desde_reference(reference: str) -> Optional[str]:
    """
    Extrae el BU correcto desde el Reference siguiendo la regla:
    'Si hay múltiples BU separados por /, tomar el SEGUNDO. Si hay uno solo, tomar ese.'
    
    Args:
        reference: String con el formato 'PREFIJO-X-####XX##.BU1[/BU2...]'
    
    Returns:
        BU inferido (str) o None si no se puede inferir
    
    Ejemplos:
        >>> inferir_bu_desde_reference('FG-R-2202LE26.M19')
        'M19'
        >>> inferir_bu_desde_reference('FG-R-2208LE26.M46/M45')
        'M45'
        >>> inferir_bu_desde_reference('FG-R-2212LE26.M01/M45')
        'M45'
    """
    if not reference or not isinstance(reference, str):
        return None
    
    # Limpiar espacios y normalizar
    ref_limpio = reference.strip()
    
    # Buscar el patrón después del último punto
    match = PATRON_BU_REFERENCE.search(ref_limpio)
    if not match:
        logger.warning(f"No se pudo extraer BU del Reference: '{reference}'")
        return None
    
    # Extraer la cadena de BUs (ej: 'M46/M45' o 'M19')
    cadena_bus = match.group(1).strip()
    
    # Dividir por '/' para obtener lista de BUs
    lista_bus = [bu.strip() for bu in cadena_bus.split("/") if bu.strip()]
    
    if not lista_bus:
        logger.warning(f"Cadena de BUs vacía en Reference: '{reference}'")
        return None
    
    # REGLA CRÍTICA:
    # - Si hay 1 solo BU → tomar ese
    # - Si hay 2 o más BUs → tomar el SEGUNDO
    if len(lista_bus) == 1:
        bu_inferido = lista_bus[0]
    else:
        bu_inferido = lista_bus[1]  # Índice 1 = segundo elemento
    
    logger.debug(f"Reference: '{reference}' → BUs detectados: {lista_bus} → BU inferido: '{bu_inferido}'")
    return bu_inferido


def inferir_bus_lote(references: List[str]) -> List[Optional[str]]:
    """
    Aplica la inferencia a una lista completa de references.
    Útil para procesar columnas enteras de un DataFrame.
    """
    return [inferir_bu_desde_reference(ref) for ref in references]


def validar_formato_reference(reference: str) -> bool:
    """
    Valida que el Reference tenga el formato esperado.
    Útil para detectar referencias mal formadas antes del procesamiento.
    """
    if not reference or not isinstance(reference, str):
        return False
    return bool(PATRON_BU_REFERENCE.search(reference.strip()))


def obtener_todos_los_bus(reference: str) -> List[str]:
    """
    Retorna TODOS los BUs presentes en un Reference (no solo el inferido).
    Útil para auditoría y validación.
    
    Ejemplo:
        >>> obtener_todos_los_bus('FG-R-2208LE26.M46/M45')
        ['M46', 'M45']
    """
    if not reference or not isinstance(reference, str):
        return []
    
    match = PATRON_BU_REFERENCE.search(reference.strip())
    if not match:
        return []
    
    return [bu.strip() for bu in match.group(1).split("/") if bu.strip()]