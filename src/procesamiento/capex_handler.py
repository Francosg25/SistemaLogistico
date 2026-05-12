"""
Manejador de la regla especial CAPEX para importaciones SEA.

REGLA DE NEGOCIO (de la hoja REGLAS_PROCESO):
═══════════════════════════════════════════════════════════════
🔴 IDENTIFICACIÓN: Item Code contiene 'CAPEX' (ej: 'CAPEX-08')
🔴 ORIGEN:        NO viene en el reporte - se agrega MANUALMENTE
🔴 BU ASIGNADO:   'Capex'
🔴 PESO:          0 (sin peso físico)
🔴 % POND:        100% (absorbe todo el costo del contenedor)
🔴 COSTO:         $2,500 USD completo por registro
═══════════════════════════════════════════════════════════════
"""
import pandas as pd
from typing import List, Dict, Union
from src.utils.logger import configurar_logger

logger = configurar_logger("capex_handler")


# Patrón que identifica un Item Code como CAPEX
PATRON_CAPEX = "CAPEX"


def es_item_capex(item_code: str) -> bool:
    """
    Determina si un Item Code corresponde a un item CAPEX.
    
    Args:
        item_code: Código del item a evaluar
    
    Returns:
        True si contiene 'CAPEX' (case-insensitive)
    
    Ejemplos:
        >>> es_item_capex('CAPEX-08')
        True
        >>> es_item_capex('1318-1030030EN')
        False
    """
    if not item_code or not isinstance(item_code, str):
        return False
    return PATRON_CAPEX.upper() in item_code.upper().strip()


def construir_registros_capex(
    contenedores_capex: List[Dict[str, str]],
    costo_fijo: float = 2500.0,
) -> pd.DataFrame:
    """
    Construye los registros CAPEX que se inyectarán al DataFrame de SEA.
    
    Cada contenedor CAPEX se convierte en un registro con:
    - BU = 'Capex'
    - Peso = 0
    - %Pond = 100%
    - Cost = $2,500 (costo fijo completo)
    
    Args:
        contenedores_capex: Lista de diccionarios con estructura:
            [
                {'Container Number': 'AMFU4236030', 'Item Code': 'CAPEX-08'},
                {'Container Number': 'TGBU7107819', 'Item Code': 'CAPEX-09'},
            ]
        costo_fijo: Costo fijo por contenedor (default $2,500)
    
    Returns:
        DataFrame con los registros CAPEX listos para inyectar
    """
    if not contenedores_capex:
        logger.info("ℹ️ No se proporcionaron contenedores CAPEX")
        return pd.DataFrame(columns=[
            "BU", "Item Code", "Container Number", 
            "Total Gross Weight", "%Pond", "Cost", "Es CAPEX"
        ])
    
    registros = []
    for capex in contenedores_capex:
        container = str(capex.get("Container Number", "")).strip()
        item_code = str(capex.get("Item Code", "")).strip()
        
        if not container or not item_code:
            logger.warning(f"⚠️ Registro CAPEX inválido (faltan datos): {capex}")
            continue
        
        # Validar que el Item Code realmente sea CAPEX
        if not es_item_capex(item_code):
            logger.warning(
                f"⚠️ Item Code '{item_code}' no contiene 'CAPEX'. "
                f"Se asignará igualmente como CAPEX por instrucción manual."
            )
        
        registro = {
            "BU": "Capex",
            "Item Code": item_code,
            "Container Number": container,
            "Total Gross Weight": 0.0,
            "%Pond": 1.0,           # 100%
            "Cost": costo_fijo,     # Absorbe todo el costo
            "Es CAPEX": True,
        }
        registros.append(registro)
    
    df_capex = pd.DataFrame(registros)
    logger.info(f"✅ {len(df_capex)} registros CAPEX construidos")
    return df_capex


def validar_contenedores_capex(
    contenedores_capex: List[Dict[str, str]],
    contenedores_en_reporte: List[str],
) -> Dict[str, List[str]]:
    """
    Valida los contenedores CAPEX ingresados manualmente.
    
    Identifica:
    - Contenedores duplicados en la lista CAPEX
    - Contenedores CAPEX que también aparecen en el reporte (¡conflicto!)
    - Contenedores con datos faltantes
    
    Returns:
        Diccionario con listas de issues encontrados
    """
    duplicados = []
    en_reporte = []
    invalidos = []
    
    containers_vistos = set()
    contenedores_reporte_set = set(c.upper() for c in contenedores_en_reporte if c)
    
    for capex in contenedores_capex:
        container = str(capex.get("Container Number", "")).strip().upper()
        item_code = str(capex.get("Item Code", "")).strip()
        
        if not container or not item_code:
            invalidos.append(f"{container or '?'} / {item_code or '?'}")
            continue
        
        if container in containers_vistos:
            duplicados.append(container)
        containers_vistos.add(container)
        
        if container in contenedores_reporte_set:
            en_reporte.append(container)
    
    return {
        "duplicados": duplicados,
        "conflicto_con_reporte": en_reporte,
        "invalidos": invalidos,
    }