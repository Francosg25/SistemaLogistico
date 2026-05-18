"""
═══════════════════════════════════════════════════════════════
MAPEO DE COLUMNAS — Sistema tolerante de alias
═══════════════════════════════════════════════════════════════
🔧 v3 — Fix definitivo para columnas duplicadas:
  1. Pre-renombra duplicados ANTES de cualquier operación
  2. Convierte explícitamente a int/float (no Series)
  3. Maneja DataFrames con columnas con el mismo nombre
═══════════════════════════════════════════════════════════════
"""
import pandas as pd
from typing import Optional, Dict, List, Tuple
from collections import Counter

from src.utils.logger import configurar_logger

logger = configurar_logger("mapeo_columnas")




COLUMNAS_POR_OPERACION = {
    "sea": {
        "criticas":   ["Container", "Item", "Peso Bruto"],
        "opcionales": ["Cantidad", "Costo", "BU"],
    },
    "land": {
        # 🔧 BU removido de críticas — se infiere desde 'Reference' (regex Mxx)
        "criticas":   ["Reference", "Item", "Peso Bruto"],
        "opcionales": ["Cantidad", "Costo", "Customer", "BU"],
    },
    "outbound": {
        # 🔧 BU removido de críticas — se infiere desde Waybill (2° BU si hay 2)
        "criticas":   ["Reference", "Item", "Peso Bruto"],
        "opcionales": ["Cantidad", "Customer", "Container", "BU"],
    },
}

ALIAS_COLUMNAS = {
    "Reference": [
        # 🔑 Waybill primero: es el más completo cuando hay duplicados
        "waybill number",
        "waybill",
        "reference",
        "ref",
        "referencia",
        "# ref",
        "reference number",
        "no ref", "no. ref", "numero referencia",
    ],
    "BU": [
        "bu",
        "business unit",
        "fix bu",
        "bu final",
    ],
    "Peso Bruto": [
        "peso bruto (kgs)",
        "gross weight (kgs)",
        "gross weight",
        "peso bruto",
        "total gross weight",
        "weight",
        "peso",
    ],
    "Item": [
        "no. parte prov.",
        "no parte prov",
        "item code",
        "item",
        "pn",
        "part number",
        "no. de parte",
    ],
    "Cantidad": [
        "qty pzas",
        "qty",
        "cantidad",
        "pieces",
        "shipped quantity",
        "total requested quantity",
    ],
    "Container": [
        "container number",
        "container",
        "no. contenedor",
        "contenedor",
    ],
    "Costo": [
        "cost (usd)",
        "fix cost",
        "cost",
        "costo",
        "amount (usd)",
        "amount",
    ],
    "Customer": [
        "customer",
        "cliente",
        "customer name",
    ],
    "Method": [
        "method",
        "metodo",
    ],
    "Inbound/Outbound": [
        "inbound/outbound",
        "tipo",
    ],
}


def buscar_columna_logica(nombre_real: str) -> Optional[str]:
    """
    Dado un nombre real de columna, busca a qué columna lógica corresponde.
    """
    if not isinstance(nombre_real, str):
        return None
    
    nombre_norm = nombre_real.strip().lower()
    if not nombre_norm:
        return None
    
    for col_logica, aliases in ALIAS_COLUMNAS.items():
        for alias in aliases:
            if nombre_norm == alias.lower():
                return col_logica
    return None


def _renombrar_duplicados_pre_mapeo(df: pd.DataFrame) -> pd.DataFrame:
    """
    🔧 CAPA 1: Pre-renombra columnas duplicadas con sufijos __dup1, __dup2.
    
    Esto garantiza que df.columns sean ÚNICAS antes de cualquier operación,
    evitando que df['col'] devuelva un DataFrame.
    """
    cols_actuales = list(df.columns)
    contador = Counter()
    nuevas_cols = []
    
    for col in cols_actuales:
        col_str = str(col)
        contador[col_str] += 1
        if contador[col_str] == 1:
            nuevas_cols.append(col_str)
        else:
            nuevo_nombre = f"{col_str}__dup{contador[col_str] - 1}"
            nuevas_cols.append(nuevo_nombre)
            logger.info(
                f"   🔁 Pre-renombrado: '{col_str}' (duplicado #{contador[col_str]-1}) "
                f"→ '{nuevo_nombre}'"
            )
    
    df_renombrado = df.copy()
    df_renombrado.columns = nuevas_cols
    return df_renombrado


def _calcular_score_columna(serie: pd.Series) -> float:
    """
    🔧 CAPA 2: Calcula el score de calidad de una columna.
    Devuelve SIEMPRE un float (nunca Series).
    """
    try:
        # Validar que sea Series (no DataFrame)
        if isinstance(serie, pd.DataFrame):
            # Si llega un DataFrame, tomar primera columna
            serie = serie.iloc[:, 0]
        
        # Contar no nulos (garantizar int)
        n_no_vacios = int(serie.notna().sum())
        
        # Longitud promedio de valores no nulos
        try:
            valores_str = serie.dropna().astype(str)
            if len(valores_str) > 0:
                longitud_promedio = float(valores_str.str.len().mean())
            else:
                longitud_promedio = 0.0
        except Exception:
            longitud_promedio = 0.0
        
        # Score final: SIEMPRE float
        score = float(n_no_vacios * 100 + longitud_promedio)
        return score
    
    except Exception as e:
        logger.warning(f"   ⚠️ Error calculando score: {e}")
        return 0.0


def mapear_columnas_dataframe(
    df: pd.DataFrame,
    operacion: Optional[str] = None,
) -> Tuple[pd.DataFrame, Dict[str, str], List[str]]:
    """
    Mapea las columnas reales del DataFrame a columnas lógicas.
    
    Con manejo robusto de duplicados:
    1. Pre-renombra duplicados con __dup1, __dup2 (garantiza unicidad)
    2. Calcula score por columna (garantiza float, no Series)
    3. Elige la mejor candidata por col_logica
    """
    # ─── CAPA 1: Pre-renombrar duplicados ───
    df = _renombrar_duplicados_pre_mapeo(df)
    
    # ─── Detectar candidatas por columna lógica ───
    # {col_logica: [(col_real, score), ...]}
    candidatas: Dict[str, List[Tuple[str, float]]] = {}
    no_mapeadas: List[str] = []
    
    for col_real in df.columns:
        # Buscar a qué col_logica corresponde
        # Quitar sufijo __dupX para buscar el alias original
        col_para_buscar = str(col_real).split("__dup")[0]
        col_logica = buscar_columna_logica(col_para_buscar)
        
        if col_logica is None:
            no_mapeadas.append(str(col_real))
            continue
        
        # 🔧 CAPA 2: Garantizar que df[col_real] sea Series
        try:
            serie = df[col_real]
            if isinstance(serie, pd.DataFrame):
                # Tomar primera columna si por algún motivo es DataFrame
                serie = serie.iloc[:, 0]
        except Exception as e:
            logger.warning(f"   ⚠️ No se pudo acceder a columna '{col_real}': {e}")
            continue
        
        # Calcular score (devuelve float garantizado)
        score = _calcular_score_columna(serie)
        
        if col_logica not in candidatas:
            candidatas[col_logica] = []
        candidatas[col_logica].append((str(col_real), score))
    
    # ─── Elegir la mejor candidata por col_logica ───
    mapeo: Dict[str, str] = {}
    duplicadas_descartadas: List[Tuple[str, str, float]] = []
    
    for col_logica, lista in candidatas.items():
        # 🔧 CAPA 3: Sort seguro (score es float garantizado)
        try:
            lista.sort(key=lambda x: -float(x[1]))
        except Exception as e:
            logger.warning(f"   ⚠️ Error ordenando candidatas de '{col_logica}': {e}")
            continue
        
        # Ganadora
        ganadora_real, ganadora_score = lista[0]
        mapeo[ganadora_real] = col_logica
        
        # Las otras → renombrar como _2, _3
        for i, (col_real, score) in enumerate(lista[1:], start=2):
            nombre_alt = f"{col_logica}_{i}"
            mapeo[col_real] = nombre_alt
            duplicadas_descartadas.append((col_real, col_logica, score))
            logger.info(
                f"   📋 Duplicado: '{col_real}' (score={score:.0f}) "
                f"perdió vs '{ganadora_real}' (score={ganadora_score:.0f}) "
                f"→ renombrado a '{nombre_alt}'"
            )
    
    # ─── Renombrar el DataFrame ───
    df_renombrado = df.rename(columns=mapeo)
    
    if mapeo:
        logger.info(f"🗂️ Columnas mapeadas: {len(mapeo)}")
    if no_mapeadas:
        logger.info(f"   ℹ️ Columnas no reconocidas (se ignoran): {len(no_mapeadas)}")
    if duplicadas_descartadas:
        logger.info(f"   ⚠️ Duplicados resueltos: {len(duplicadas_descartadas)}")
    
    return df_renombrado, mapeo, no_mapeadas


# ════════════════════════════════════════════════════════════
# HELPERS DE VALIDACIÓN
# ════════════════════════════════════════════════════════════
# ════════════════════════════════════════════════════════════
# HELPERS DE VALIDACIÓN
# ════════════════════════════════════════════════════════════
def validar_columnas_criticas(
    df: pd.DataFrame,
    operacion: Optional[str] = None,
) -> Tuple[bool, List[str], List[str]]:
    """
    Valida que las columnas críticas estén presentes en el DataFrame.
    
    🔧 v2 — Devuelve 3 valores (compatible con lector_excel.py):
        - es_valido: bool, True si todas las críticas están presentes
        - faltantes_criticas: list, columnas críticas que faltan
        - faltantes_opcionales: list, columnas opcionales que faltan (info)
    
    Args:
        df: DataFrame con columnas YA MAPEADAS (lógicas)
        operacion: 'sea', 'land' u 'outbound'
    
    Returns:
        Tupla (es_valido, faltantes_criticas, faltantes_opcionales)
    """
    # Obtener configuración de la operación
    config = COLUMNAS_POR_OPERACION.get(
        (operacion or "").lower(),
        {"criticas": ["Reference", "Item", "Peso Bruto"], "opcionales": []}
    )
    
    # Soportar formato dict (nuevo) y lista (legacy)
    if isinstance(config, dict):
        criticas = config.get("criticas", [])
        opcionales = config.get("opcionales", [])
    elif isinstance(config, list):
        criticas = config
        opcionales = []
    else:
        criticas = []
        opcionales = []
    
    # Detectar faltantes
    faltantes_criticas = [c for c in criticas if c not in df.columns]
    faltantes_opcionales = [c for c in opcionales if c not in df.columns]
    
    es_valido = len(faltantes_criticas) == 0
    
    if faltantes_criticas:
        logger.warning(
            f"   ⚠️ Faltan columnas críticas para '{operacion}': {faltantes_criticas}"
        )
    if faltantes_opcionales:
        logger.info(
            f"   ℹ️ Columnas opcionales no encontradas: {faltantes_opcionales}"
        )
    
    return es_valido, faltantes_criticas, faltantes_opcionales

def calcular_score_hoja(
    df: pd.DataFrame,
    operacion: Optional[str] = None,
    columnas_criticas: Optional[List[str]] = None,
) -> Dict:
    """
    Calcula un score de qué tan probable es que una hoja sea la correcta
    para una operación (sea/land/outbound).
    
    Args:
        df: DataFrame con las columnas YA MAPEADAS (lógicas)
        operacion: 'sea', 'land' u 'outbound'
        columnas_criticas: Lista opcional de columnas críticas a buscar
    
    Returns:
        Dict con score, presentes, faltantes, n_filas, n_criticas_total
    """
    # Lee del dict COLUMNAS_POR_OPERACION si no se especifica
    if columnas_criticas is None:
        config_operacion = COLUMNAS_POR_OPERACION.get(
            (operacion or "").lower(),
            {"criticas": ["Reference", "Item", "Peso Bruto"]}
        )
        # 🔧 FIX: Esta línea va DENTRO del if (4 espacios más)
        columnas_criticas = config_operacion.get("criticas", [])
    
    # Detectar qué columnas críticas están presentes
    presentes = [c for c in columnas_criticas if c in df.columns]
    faltantes = [c for c in columnas_criticas if c not in df.columns]
    
    # Cálculo del score
    # +10 por cada columna crítica presente
    # +1 por cada fila con datos (bonus por tamaño, max 30)
    score_columnas = len(presentes) * 10
    score_filas = min(len(df), 30)  # max 30 puntos por filas
    score_total = score_columnas + score_filas
    
    return {
        "score": score_total,
        "presentes": presentes,
        "faltantes": faltantes,
        "n_filas": len(df),
        "n_criticas_total": len(columnas_criticas),
        "n_criticas_presentes": len(presentes),
    }

def columnas_logicas_disponibles() -> List[str]:
    """
    Devuelve la lista de columnas lógicas que el sistema reconoce.
    Útil para diagnóstico y documentación.
    """
    return list(ALIAS_COLUMNAS.keys())
