"""Validador de columnas obligatorias."""
import pandas as pd
from typing import List, Dict
from src.ingesta.excepciones import ColumnaFaltanteError


COLUMNAS_OBLIGATORIAS = {
    "sea": [
        "BU",
        "Item Code",
        "Container Number",
        "Total Gross Weight",
    ],
    "land": [
        "Inbound/Outbound",
        "Method",
        "Reference",
        "BU",
        "Peso Bruto (Kgs)",
        "No. Parte Prov.",
    ],
    "outbound": [
        # 🔧 Quitamos Waybill Number de obligatorias (se reconstruye desde Reference)
        "Inbound/Outbound",
        "Method",
        "Reference",
        "BU",
        "Gross Weight",
        "Item",
        "Qty Pzas",
    ],
}


import pandas as pd
from typing import List, Dict
from src.ingesta.excepciones import ColumnaFaltanteError
from src.ingesta.mapeo_columnas import (
    validar_columnas_criticas,
    COLUMNAS_POR_OPERACION,
)


def validar_columnas(df: pd.DataFrame, tipo_operacion: str) -> None:
    """
    Valida que el DataFrame tenga las columnas críticas para la operación.
    Lanza ColumnaFaltanteError si falta alguna crítica.
    """
    es_valido, faltantes_crit, _ = validar_columnas_criticas(df, tipo_operacion.lower())
    
    if not es_valido:
        raise ColumnaFaltanteError(faltantes_crit, tipo_operacion)


def obtener_resumen_columnas(df: pd.DataFrame) -> Dict:
    return {
        "total_columnas": len(df.columns),
        "columnas": list(df.columns),
        "total_filas": len(df),
        "filas_con_datos": int(df.notna().any(axis=1).sum()),
    }


def obtener_resumen_columnas(df: pd.DataFrame) -> Dict[str, any]:
    return {
        "total_columnas": len(df.columns),
        "columnas": list(df.columns),
        "total_filas": len(df),
        "filas_con_datos": int(df.notna().any(axis=1).sum()),
    }
