"""
Validador de columnas obligatorias.
Verifica que el archivo cargado contenga las columnas mínimas requeridas.
"""
import pandas as pd
from typing import List, Dict
from src.ingesta.excepciones import ColumnaFaltanteError


# === Columnas obligatorias por tipo de operación ===
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
        "Inbound/Outbound",
        "Method",
        "Reference",
        "BU",
        "Gross Weight",
        "Waybill Number",
        "Item",
        "Qty Pzas",
    ],
}


def validar_columnas(df: pd.DataFrame, tipo_operacion: str) -> None:
    """
    Verifica que el DataFrame contenga las columnas obligatorias.
    
    Args:
        df: DataFrame a validar
        tipo_operacion: 'sea', 'land' u 'outbound'
    
    Raises:
        ColumnaFaltanteError: Si faltan columnas obligatorias
    """
    tipo = tipo_operacion.lower()
    if tipo not in COLUMNAS_OBLIGATORIAS:
        raise ValueError(f"Tipo de operación desconocido: {tipo_operacion}")
    
    requeridas = COLUMNAS_OBLIGATORIAS[tipo]
    columnas_df = [str(c).strip() for c in df.columns]
    faltantes = [col for col in requeridas if col not in columnas_df]
    
    if faltantes:
        raise ColumnaFaltanteError(faltantes, tipo_operacion)


def obtener_resumen_columnas(df: pd.DataFrame) -> Dict[str, any]:
    """Retorna un resumen útil para debugging."""
    return {
        "total_columnas": len(df.columns),
        "columnas": list(df.columns),
        "total_filas": len(df),
        "filas_con_datos": int(df.notna().any(axis=1).sum()),
    }
