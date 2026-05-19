"""
═══════════════════════════════════════════════════════════════
MAPEO DE COLUMNAS — Sistema adaptativo de aliases
═══════════════════════════════════════════════════════════════
🔄 COMPATIBILIDAD HACIA ATRÁS COMPLETA:
   - buscar_columna_logica()         ✅ legacy
   - mapear_columnas_dataframe()     ✅ legacy (devuelve TUPLA 3)
   - calcular_score_hoja()           ✅ legacy (devuelve DICT)
   - obtener_columnas_canonicas()    ✅ legacy
   - normalizar_nombre_columna()     ✅ legacy
   - validar_columnas_criticas()     ✅ legacy
   - COLUMNAS_POR_OPERACION          ✅ legacy (formato DICT)
═══════════════════════════════════════════════════════════════
"""
import re
import pandas as pd
from typing import Dict, List, Tuple, Optional, Union
from dataclasses import dataclass, field


# ════════════════════════════════════════════════════════════
# DICCIONARIO MAESTRO DE ALIASES
# ════════════════════════════════════════════════════════════
ALIASES_CANONICOS: Dict[str, List[str]] = {
    "Reference": [
        "Referencia", "Reference", "Ref", "No. Referencia",
        "Ref Number", "Shipping Reference", "REF", "REF#",
    ],
    "Container": [
        "Container Number", "Container", "Caja", "Contenedor",
        "No. Caja", "Box", "CONT", "BOX",
    ],
    "Waybill": [
        "Waybill Number", "Waybill", "Guía", "Guia",
        "No. Guía", "No. Guia", "AWB", "BL", "WB", "WBL",
    ],
    "Item": [
        "Item", "Item Code", "No. Parte", "No. Parte Prov.",
        "Código", "Codigo", "Part Number", "PN", "ITEM",
    ],
    "Subinventory": [
        "Subinventory", "Subinv", "Subinventario",
        "Almacén", "Almacen", "Warehouse", "SUBINV", "WH",
        "Codigo Suc.",
    ],
    "Pieces": [
        "Pieces", "Qty", "Quantity", "Pcs", "Piezas",
        "Bultos", "Cantidad", "Qty Pzas", "PCS", "QTY",
    ],
    "Gross_Weight": [
        "Gross Weight", "Gross Weight (Kgs)", "Peso Bruto",
        "Peso Bruto (Kgs)", "Total Gross Weight",
        "Carton Gross Weight", "PB", "GW",
    ],
    "Net_Weight": [
        "Net Weight", "Net Weight (Kgs)", "Peso Neto",
        "Peso Neto (Kgs)", "NW",
    ],
    "Amount": [
        "Amount", "Invoice Amount", "Importe", "Monto",
        "Valor", "Value", "AMT", "VAL", "Cost", "Cost (USD)",
    ],
    "Currency": ["Currency", "Moneda", "Divisa", "CCY"],
    "Transport_Name": [
        "Transport Name", "Carrier", "Line", "Transporte",
        "Línea", "Linea", "TRANS",
    ],
    "Customer": [
        "Customer", "Ship To", "Consignee", "Cliente",
        "Destinatario", "Nombre Cliente", "CUST",
    ],
    "Date_OnBoard": [
        "On Board", "On Board Date", "ETD",
        "Fecha Embarque", "Fecha Cruce",
    ],
    "Description": [
        "Description", "Item Description",
        "Descripcion Parte Prov.", "Descripción", "DESC",
    ],
    "BU": ["BU", "Business Unit", "Unidad Negocio", "Fix BU"],
    "Method": ["Method", "Método", "Metodo", "Modo"],
    "Inbound_Outbound": ["Inbound/Outbound", "IO", "Direction"],
}


# ════════════════════════════════════════════════════════════
# CONFIGURACIÓN POR OPERACIÓN (formato DICT con peso por columna)
# ════════════════════════════════════════════════════════════
# Estructura esperada por detector_hojas.py:
#   {
#     "criticas":   [columnas obligatorias],
#     "opcionales": [columnas recomendadas],
#     "pesos":      {columna: score_si_existe},
#   }
COLUMNAS_POR_OPERACION: Dict[str, Dict] = {
    "sea": {
        "criticas":   ["Item", "Container", "Gross_Weight"],
        "opcionales": ["Subinventory", "BU", "Pieces", "Description"],
        "pesos": {
            "Item": 10,
            "Container": 15,
            "Gross_Weight": 10,
            "Subinventory": 8,
            "BU": 5,
            "Pieces": 3,
            "Description": 2,
        },
    },
    "land": {
        "criticas":   ["Reference", "Item", "Gross_Weight"],
        "opcionales": ["Container", "BU", "Pieces", "Customer"],
        "pesos": {
            "Reference": 15,
            "Item": 10,
            "Gross_Weight": 10,
            "Container": 8,
            "BU": 5,
            "Pieces": 3,
            "Customer": 2,
        },
    },
    "outbound": {
        "criticas":   ["Reference", "Item", "Gross_Weight"],
        "opcionales": ["Waybill", "Customer", "Container", "BU", "Pieces"],
        "pesos": {
            "Waybill": 15,
            "Reference": 10,
            "Item": 8,
            "Gross_Weight": 8,
            "Customer": 5,
            "Container": 3,
            "BU": 3,
            "Pieces": 2,
        },
    },
}

# Alias legacy (algunos módulos pueden esperar listas simples)
OBLIGATORIAS_POR_OP: Dict[str, List[str]] = {
    op: cfg["criticas"] for op, cfg in COLUMNAS_POR_OPERACION.items()
}


# ════════════════════════════════════════════════════════════
# DATA CLASSES
# ════════════════════════════════════════════════════════════
@dataclass
class ResultadoMapeo:
    """Resultado de aplicar el mapeo a un DataFrame."""
    df: pd.DataFrame
    mapeo: Dict[str, str] = field(default_factory=dict)
    encontradas: List[str] = field(default_factory=list)
    faltantes: List[str] = field(default_factory=list)
    no_mapeadas: List[str] = field(default_factory=list)
    es_valido: bool = False


# ════════════════════════════════════════════════════════════
# FUNCIONES CORE
# ════════════════════════════════════════════════════════════
def _normalizar(texto) -> str:
    """Normaliza: trim + lower + colapsa espacios + quita acentos."""
    if texto is None:
        return ""
    s = str(texto).strip().lower()
    s = re.sub(r"\s+", " ", s)
    reemplazos = {
        "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ñ": "n",
    }
    for k, v in reemplazos.items():
        s = s.replace(k, v)
    return s


def normalizar_nombre_columna(texto: str) -> str:
    """🔄 Compatibilidad: versión pública de _normalizar()."""
    return _normalizar(texto)


def detectar_columna(
    columnas_df: List[str],
    alias_list: List[str],
) -> Optional[str]:
    """
    Busca cualquier alias en las columnas del df.
    Retorna la columna ORIGINAL del df que matchea, o None.
    """
    normalizadas = {_normalizar(c): c for c in columnas_df}
    for alias in alias_list:
        alias_norm = _normalizar(alias)
        if alias_norm in normalizadas:
            return normalizadas[alias_norm]
    return None


# ════════════════════════════════════════════════════════════
# 🔄 FUNCIONES DE COMPATIBILIDAD LEGACY
# ════════════════════════════════════════════════════════════
def buscar_columna_logica(
    *args,
    **kwargs,
) -> Optional[str]:
    """
    🔄 Compatibilidad POLIMÓRFICA con múltiples APIs legacy.

    Soporta DOS modos de uso distintos:

    MODO A — Búsqueda directa (API moderna):
        buscar_columna_logica(columnas_df, nombre_logico) → "Container Number"
        buscar_columna_logica(df, "Container")            → "Container Number"

        Args:
            - df_o_columnas: DataFrame o list[str] con nombres de columnas
            - nombre_logico: str con el nombre canónico ("Reference", "Container", ...)
            - aliases_extra: list[str] opcional

        Returns:
            El nombre real de la columna en el DataFrame, o None.

    MODO B — Clasificación inversa (API legacy de detector_header.py):
        buscar_columna_logica("Container Number")     → "Container"
        buscar_columna_logica("Peso Bruto (Kgs)")     → "Gross_Weight"
        buscar_columna_logica("xyz_no_existe")        → None

        Args:
            - valor_celda: str con el nombre de una columna entrante

        Returns:
            El nombre CANÓNICO al que pertenece, o None si no coincide.
    """
    # ────────────────────────────────────────────────────
    # Detectar modo según número y tipo de argumentos
    # ────────────────────────────────────────────────────
    df_o_columnas = kwargs.get("df_o_columnas")
    nombre_logico = kwargs.get("nombre_logico")
    aliases_extra = kwargs.get("aliases_extra")
    valor_celda = kwargs.get("valor_celda")

    # Asignar positional args si no llegaron por kwargs
    if df_o_columnas is None and nombre_logico is None and valor_celda is None:
        if len(args) == 1:
            # MODO B: clasificación inversa (1 solo string)
            valor_celda = args[0]
        elif len(args) >= 2:
            # MODO A: búsqueda directa
            df_o_columnas = args[0]
            nombre_logico = args[1]
            if len(args) >= 3:
                aliases_extra = args[2]

    # ════════════════════════════════════════════════════
    # MODO B: Clasificación inversa
    #   Recibe un valor de celda y devuelve a qué canónica pertenece
    # ════════════════════════════════════════════════════
    if valor_celda is not None or (
        df_o_columnas is not None
        and nombre_logico is None
        and isinstance(df_o_columnas, str)
    ):
        # Si vino solo un str positional, está en df_o_columnas — corregir
        if valor_celda is None:
            valor_celda = df_o_columnas

        if valor_celda is None:
            return None

        valor_norm = _normalizar(valor_celda)
        if not valor_norm:
            return None

        # Recorrer las canónicas y ver cuál tiene este alias
        for canonica, aliases in ALIASES_CANONICOS.items():
            for alias in aliases:
                if _normalizar(alias) == valor_norm:
                    return canonica
        return None

    # ════════════════════════════════════════════════════
    # MODO A: Búsqueda directa
    #   Recibe una lista de columnas y un nombre canónico
    # ════════════════════════════════════════════════════
    if df_o_columnas is None or nombre_logico is None:
        return None

    if isinstance(df_o_columnas, pd.DataFrame):
        columnas = list(df_o_columnas.columns)
    else:
        columnas = list(df_o_columnas)

    aliases = ALIASES_CANONICOS.get(nombre_logico, [])
    if aliases_extra:
        aliases = list(aliases) + list(aliases_extra)
    if not aliases:
        aliases = [nombre_logico]

    return detectar_columna(columnas, aliases)


# ════════════════════════════════════════════════════════════
# MAPA DE NOMBRES LEGACY (para retro-compatibilidad con lector_excel.py)
# ════════════════════════════════════════════════════════════
# Estos son los nombres que el código LEGACY (lector_excel.py, procesar_*.py)
# espera DESPUÉS del renombrado. Permite que ambos mundos coexistan.
NOMBRES_LEGACY: Dict[str, str] = {
    "Reference":       "Reference",       # igual
    "Container":       "Container",       # igual
    "Waybill":         "Waybill Number",  # legacy
    "Item":            "Item",            # igual
    "Subinventory":    "Subinventory",    # igual
    "Pieces":          "Cantidad",        # legacy
    "Gross_Weight":    "Peso Bruto",      # 🔑 legacy en español
    "Net_Weight":      "Peso Neto",       # legacy
    "Amount":          "Amount",          # igual
    "Currency":        "Currency",        # igual
    "Transport_Name":  "Transporte",      # legacy
    "Customer":        "Customer",        # igual
    "Date_OnBoard":    "Fecha Embarque",  # legacy
    "Description":     "Description",     # igual
    "BU":              "BU",              # igual
    "Method":          "Method",          # igual
    "Inbound_Outbound":"Inbound/Outbound",# igual
}


def mapear_columnas_dataframe(
    df: pd.DataFrame,
    operacion: Optional[str] = None,
    renombrar: bool = True,
    usar_nombres_legacy: bool = True,   # 🔑 NUEVO: por default usa legacy
) -> Tuple[pd.DataFrame, Dict[str, str], List[str]]:
    """
    🔄 Compatibilidad con detector_hojas.py y lector_excel.py.

    Devuelve TUPLA de 3 elementos:
        (df_mapeado, mapeo, columnas_no_mapeadas)

    El mapeo es: {columna_original_del_df: nombre_lógico}

    Args:
        df: DataFrame con columnas en cualquier variante
        operacion: 'sea' | 'land' | 'outbound' (opcional, para info)
        renombrar: si True, renombra columnas al nombre objetivo
        usar_nombres_legacy: si True (default), renombra a nombres LEGACY
                             (ej. "Peso Bruto" en vez de "Gross_Weight")
                             para compatibilidad con lector_excel.py.
                             Si False, usa nombres CANÓNICOS modernos.

    Returns:
        (df_resultado, mapeo, no_mapeadas)
    """
    columnas_df = list(df.columns)
    mapeo: Dict[str, str] = {}  # {col_original: nombre_canonico}

    for canonica, aliases in ALIASES_CANONICOS.items():
        col_original = detectar_columna(columnas_df, aliases)
        if col_original is not None:
            mapeo[col_original] = canonica

    mapeadas_originales = set(mapeo.keys())
    no_mapeadas = [c for c in columnas_df if c not in mapeadas_originales]

    df_resultado = df.copy()
    if renombrar and mapeo:
        if usar_nombres_legacy:
            # 🔑 Renombrar a nombres LEGACY (lector_excel.py los espera)
            mapeo_renombrar = {
                col_orig: NOMBRES_LEGACY.get(canonica, canonica)
                for col_orig, canonica in mapeo.items()
            }
        else:
            # Renombrar a nombres canónicos modernos
            mapeo_renombrar = mapeo.copy()

        df_resultado = df_resultado.rename(columns=mapeo_renombrar)

    return df_resultado, mapeo, no_mapeadas


def calcular_score_hoja(
    df: pd.DataFrame,
    operacion: str,
) -> Dict:
    """
    🔄 Compatibilidad con detector_hojas.py legacy.

    Calcula un score de qué tan probable es que el DataFrame sea
    de la operación indicada.

    Estrategia:
      - Cada columna lógica encontrada suma su peso configurado
      - Las columnas CRÍTICAS no presentes restan puntos
      - El score se ajusta por # filas (penaliza hojas casi vacías)

    Returns:
        dict con:
        - score:        int (0-100+)
        - presentes:    list de columnas lógicas detectadas
        - faltantes:    list de columnas críticas faltantes
        - bonus_filas:  int (puntos extra por # de filas)
    """
    op = operacion.lower()
    config = COLUMNAS_POR_OPERACION.get(op, {})

    criticas: List[str] = config.get("criticas", [])
    pesos: Dict[str, int] = config.get("pesos", {})

    # Detectar qué columnas lógicas están presentes
    columnas_df = list(df.columns)
    presentes: List[str] = []
    for canonica, aliases in ALIASES_CANONICOS.items():
        if detectar_columna(columnas_df, aliases) is not None:
            presentes.append(canonica)

    # Calcular score base con pesos
    score = 0
    for col_logica in presentes:
        score += pesos.get(col_logica, 1)

    # Penalizar críticas faltantes (cada una resta 10 puntos)
    faltantes = [c for c in criticas if c not in presentes]
    score -= len(faltantes) * 10

    # Bonus por # de filas (hojas vacías = score más bajo)
    num_filas = len(df)
    bonus_filas = 0
    if num_filas >= 5:
        bonus_filas = 5
    if num_filas >= 50:
        bonus_filas = 10
    if num_filas >= 200:
        bonus_filas = 15
    score += bonus_filas

    # No permitir scores negativos
    score = max(score, 0)

    return {
        "score": int(score),
        "presentes": presentes,
        "faltantes": faltantes,
        "bonus_filas": bonus_filas,
        "num_filas": num_filas,
    }


def obtener_columnas_canonicas(
    df: pd.DataFrame,
    operacion: Optional[str] = None,
) -> Dict[str, str]:
    """🔄 Compatibilidad: retorna {canonica: columna_original}."""
    columnas_df = list(df.columns)
    mapeo: Dict[str, str] = {}
    for canonica, aliases in ALIASES_CANONICOS.items():
        col_original = detectar_columna(columnas_df, aliases)
        if col_original is not None:
            mapeo[canonica] = col_original
    return mapeo


def contar_columnas_canonicas(df: pd.DataFrame) -> int:
    """🔄 Compatibilidad: cuenta columnas canónicas reconocidas."""
    return len(obtener_columnas_canonicas(df))


def es_dataframe_valido(
    df: pd.DataFrame,
    operacion: str,
    min_columnas_canonicas: int = 3,
) -> Tuple[bool, List[str]]:
    """🔄 Compatibilidad: verifica si un df parece de la operación."""
    mapeo = obtener_columnas_canonicas(df)

    op = operacion.lower()
    if op not in COLUMNAS_POR_OPERACION:
        return False, [f"Operación desconocida: {operacion}"]

    obligatorias = COLUMNAS_POR_OPERACION[op].get("criticas", [])
    faltantes = [c for c in obligatorias if c not in mapeo]

    es_valido = (
        len(faltantes) == 0
        and len(mapeo) >= min_columnas_canonicas
    )
    return es_valido, faltantes


# ════════════════════════════════════════════════════════════
# API NUEVA (uso recomendado)
# ════════════════════════════════════════════════════════════
def aplicar_mapeo(
    df: pd.DataFrame,
    operacion: str,
    renombrar: bool = True,
) -> ResultadoMapeo:
    """API NUEVA: mapeo con reporte estructurado."""
    op = operacion.lower()
    if op not in COLUMNAS_POR_OPERACION:
        raise ValueError(f"Operación desconocida: {operacion}")

    columnas_df = list(df.columns)
    mapeo_logico_a_original: Dict[str, str] = {}
    encontradas: List[str] = []
    faltantes: List[str] = []

    criticas = COLUMNAS_POR_OPERACION[op].get("criticas", [])

    for canonica, aliases in ALIASES_CANONICOS.items():
        col_original = detectar_columna(columnas_df, aliases)
        if col_original is not None:
            mapeo_logico_a_original[canonica] = col_original
            encontradas.append(canonica)
        else:
            if canonica in criticas:
                faltantes.append(canonica)

    mapeadas_originales = set(mapeo_logico_a_original.values())
    no_mapeadas = [c for c in columnas_df if c not in mapeadas_originales]

    df_resultado = df.copy()
    if renombrar:
        inv_mapeo = {v: k for k, v in mapeo_logico_a_original.items()}
        df_resultado = df_resultado.rename(columns=inv_mapeo)

    return ResultadoMapeo(
        df=df_resultado,
        mapeo=mapeo_logico_a_original,
        encontradas=encontradas,
        faltantes=faltantes,
        no_mapeadas=no_mapeadas,
        es_valido=(len(faltantes) == 0),
    )


def validar_columnas_criticas(
    df: pd.DataFrame,
    operacion: str,
) -> Tuple[bool, List[str], List[str]]:
    """
    🔄 Compatibilidad con lector_excel.py.
    
    Valida que las columnas críticas (en nombres LEGACY) existan en el df.
    
    Returns:
        (es_valido, faltantes_criticas, faltantes_opcionales)
    """
    op = operacion.lower()
    if op not in COLUMNAS_POR_OPERACION:
        return False, [f"Operación desconocida: {operacion}"], []

    config = COLUMNAS_POR_OPERACION[op]
    criticas_canonicas = config.get("criticas", [])
    opcionales_canonicas = config.get("opcionales", [])

    # Traducir canónicas → legacy (lo que está en el df)
    criticas_legacy = [
        NOMBRES_LEGACY.get(c, c) for c in criticas_canonicas
    ]
    opcionales_legacy = [
        NOMBRES_LEGACY.get(c, c) for c in opcionales_canonicas
    ]

    columnas_df = list(df.columns)
    faltantes_criticas = [c for c in criticas_legacy if c not in columnas_df]
    faltantes_opcionales = [c for c in opcionales_legacy if c not in columnas_df]

    es_valido = len(faltantes_criticas) == 0
    return es_valido, faltantes_criticas, faltantes_opcionales


# ════════════════════════════════════════════════════════════
# EXPORTS PÚBLICOS
# ════════════════════════════════════════════════════════════
__all__ = [
    # Constantes
    "ALIASES_CANONICOS",
    "COLUMNAS_POR_OPERACION",
    "OBLIGATORIAS_POR_OP",
    # Data classes
    "ResultadoMapeo",
    # API nueva
    "detectar_columna",
    "aplicar_mapeo",
    "validar_columnas_criticas",
    # 🔄 Compatibilidad legacy (necesarias para detector_hojas/header)
    "buscar_columna_logica",
    "mapear_columnas_dataframe",
    "calcular_score_hoja",
    "obtener_columnas_canonicas",
    "normalizar_nombre_columna",
    "contar_columnas_canonicas",
    "es_dataframe_valido",
]