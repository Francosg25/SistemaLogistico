"""
═══════════════════════════════════════════════════════════════
SISTEMA DE ALIAS DE COLUMNAS
═══════════════════════════════════════════════════════════════
Permite que el sistema acepte múltiples nombres para la misma
columna lógica (case-insensitive, sin acentos, sin espacios extra).

Ejemplo:
    Si el archivo tiene "Referencia", "Ref" o "Reference Number"
    → todas se mapean a la columna lógica "Reference"
═══════════════════════════════════════════════════════════════
"""
import re
import unicodedata
from typing import Dict, List, Optional, Tuple
import pandas as pd

from src.utils.logger import configurar_logger

logger = configurar_logger("mapeo_columnas")


# ════════════════════════════════════════════════════════════
# DICCIONARIO DE ALIAS — Replica la Sección 10 de REGLAS_PROCESO
# ════════════════════════════════════════════════════════════
ALIAS_COLUMNAS = {
    "Reference": [
        "reference", "ref", "referencia", "# ref", "reference number",
        "waybill", "waybill number", "no ref", "no. ref", "numero referencia",
    ],
    "BU": [
        "bu", "business unit", "b.u.", "b u", "unidad de negocio",
        "fix bu", "bu final", "bu detectado",
    ],
    "Peso Bruto": [
        "peso bruto (kgs)", "peso bruto kgs", "peso bruto", "gross weight",
        "weight", "peso", "total gross weight", "peso bruto kg",
        "gross weight (kgs)", "kg", "kgs",
    ],
    "Item": [
        "item", "item code", "no. parte", "no parte", "no. parte prov.",
        "no parte prov", "part number", "pn", "descripcion parte prov.",
        "descripcion parte", "no. parte prov", "no.parte prov", "no. pte. impo",
    ],
    "Container": [
        "container", "container number", "# container", "contenedor",
        "no contenedor", "no. contenedor",
    ],
    "Customer": [
        "customer", "cliente", "nombre cliente", "customer name",
        "client", "razon social",
    ],
    "Cantidad": [
        "qty", "qty pzas", "cantidad", "pieces", "bultos", "piezas",
        "qty piezas", "quantity",
    ],
    "Costo": [
        "cost", "cost (usd)", "fix cost", "container cost", "amount",
        "monto", "costo", "costo (usd)", "amount (usd)", "monto (usd)",
    ],
    "Inbound/Outbound": [
        "inbound/outbound", "in/out", "direction", "tipo", "tipo movimiento",
        "movimiento",
    ],
    "Method": [
        "method", "modo", "transport method", "transporte", "metodo",
        "metodo transporte",
    ],
    "Subinventory": [
        "subinventory", "sub inv", "sub-inventory", "inventario",
        "almacen", "almacén",
    ],
    "Caja": [
        "caja", "caja scan", "box", "carton",
    ],
}


# ════════════════════════════════════════════════════════════
# COLUMNAS REQUERIDAS / OPCIONALES por operación
# ════════════════════════════════════════════════════════════
COLUMNAS_POR_OPERACION = {
    "land": {
        "criticas": ["Reference", "Peso Bruto", "Item"],
        "opcionales": ["BU", "Caja", "Method", "Cantidad"],
    },
    "outbound": {
        "criticas": ["Reference", "Peso Bruto", "Item"],
        "opcionales": ["BU", "Customer", "Method", "Cantidad", "Container"],
    },
    "sea": {
        "criticas": ["Container", "Peso Bruto", "Item"],
        "opcionales": ["BU", "Subinventory", "Costo"],
    },
}


# ════════════════════════════════════════════════════════════
# FUNCIONES DE NORMALIZACIÓN
# ════════════════════════════════════════════════════════════
def normalizar_nombre_columna(nombre: str) -> str:
    """
    Normaliza un nombre de columna para comparación robusta:
    - Convierte a minúsculas
    - Quita acentos
    - Reemplaza múltiples espacios por uno
    - Quita espacios al inicio/fin
    - Quita caracteres no alfanuméricos al inicio/fin
    
    Ejemplos:
        "  Reference Number  " → "reference number"
        "Peso Bruto (Kgs)"     → "peso bruto (kgs)"
        "REFERENCIA"           → "referencia"
    """
    if nombre is None:
        return ""
    
    s = str(nombre).strip().lower()
    
    # Quitar acentos
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    
    # Normalizar espacios
    s = re.sub(r"\s+", " ", s)
    s = s.strip()
    
    return s


def buscar_columna_logica(nombre_real: str) -> Optional[str]:
    """
    Dado un nombre de columna del archivo, devuelve la columna lógica
    correspondiente (o None si no se reconoce).
    
    Ejemplos:
        buscar_columna_logica("Referencia")     → "Reference"
        buscar_columna_logica("gross weight")   → "Peso Bruto"
        buscar_columna_logica("Mi Columna XYZ") → None
    """
    if not nombre_real:
        return None
    
    nombre_norm = normalizar_nombre_columna(nombre_real)
    if not nombre_norm:
        return None
    
    for columna_logica, aliases in ALIAS_COLUMNAS.items():
        for alias in aliases:
            if normalizar_nombre_columna(alias) == nombre_norm:
                return columna_logica
    
    return None


def mapear_columnas_dataframe(
    df: pd.DataFrame,
    operacion: Optional[str] = None,
) -> Tuple[pd.DataFrame, Dict[str, str], List[str]]:
    """
    Mapea las columnas reales del DataFrame a columnas lógicas.
    
    Args:
        df: DataFrame con nombres de columna del archivo
        operacion: 'land', 'outbound' o 'sea' (para validar críticas)
    
    Returns:
        Tupla:
          - df_renombrado: DataFrame con columnas lógicas
          - mapeo: dict {col_real: col_logica}
          - columnas_no_mapeadas: lista de columnas que no se reconocieron
    """
    mapeo = {}
    no_mapeadas = []
    
    for col_real in df.columns:
        col_logica = buscar_columna_logica(col_real)
        if col_logica:
            # Si ya existe esta columna lógica (duplicado), agregar sufijo
            if col_logica in mapeo.values():
                contador = 2
                while f"{col_logica}_{contador}" in mapeo.values():
                    contador += 1
                mapeo[col_real] = f"{col_logica}_{contador}"
                logger.warning(
                    f"   ⚠️ Columna duplicada: '{col_real}' → '{col_logica}_{contador}' "
                    f"(ya existía '{col_logica}')"
                )
            else:
                mapeo[col_real] = col_logica
        else:
            no_mapeadas.append(col_real)
    
    # Renombrar
    df_renombrado = df.rename(columns=mapeo)
    
    # Logging
    if mapeo:
        logger.info(f"🗂️ Columnas mapeadas: {len(mapeo)}")
        for real, logica in mapeo.items():
            if real != logica:
                logger.debug(f"   '{real}' → '{logica}'")
    
    if no_mapeadas:
        logger.info(f"   ℹ️ Columnas no reconocidas (se ignoran): {len(no_mapeadas)}")
    
    return df_renombrado, mapeo, no_mapeadas


def validar_columnas_criticas(
    df: pd.DataFrame,
    operacion: str,
) -> Tuple[bool, List[str], List[str]]:
    """
    Valida que el DataFrame tenga las columnas críticas para la operación.
    
    Returns:
        Tupla:
          - es_valido: True si tiene todas las críticas
          - faltantes_criticas: lista de columnas críticas faltantes
          - faltantes_opcionales: lista de columnas opcionales faltantes
    """
    if operacion not in COLUMNAS_POR_OPERACION:
        return True, [], []
    
    config = COLUMNAS_POR_OPERACION[operacion]
    columnas_presentes = set(df.columns)
    
    faltantes_criticas = [
        c for c in config["criticas"] if c not in columnas_presentes
    ]
    faltantes_opcionales = [
        c for c in config["opcionales"] if c not in columnas_presentes
    ]
    
    es_valido = len(faltantes_criticas) == 0
    return es_valido, faltantes_criticas, faltantes_opcionales


def calcular_score_hoja(df: pd.DataFrame, operacion: str) -> int:
    """
    Calcula un score numérico de qué tan probable es que esta hoja
    pertenezca a la operación indicada.
    
    Score:
      +10 por cada columna crítica presente
      +3 por cada columna opcional presente
      -5 si faltan TODAS las críticas
    """
    if operacion not in COLUMNAS_POR_OPERACION:
        return 0
    
    config = COLUMNAS_POR_OPERACION[operacion]
    columnas_presentes = set(df.columns)
    
    score = 0
    criticas_presentes = sum(1 for c in config["criticas"] if c in columnas_presentes)
    opcionales_presentes = sum(1 for c in config["opcionales"] if c in columnas_presentes)
    
    score += criticas_presentes * 10
    score += opcionales_presentes * 3
    
    if criticas_presentes == 0:
        score -= 5
    
    return score