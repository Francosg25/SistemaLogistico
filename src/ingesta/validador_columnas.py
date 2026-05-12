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


def validar_columnas(df: pd.DataFrame, tipo_operacion: str) -> None:
    tipo = tipo_operacion.lower()
    if tipo not in COLUMNAS_OBLIGATORIAS:
        raise ValueError(f"Tipo de operación desconocido: {tipo_operacion}")
    
    requeridas = COLUMNAS_OBLIGATORIAS[tipo]
    columnas_df = [str(c).strip() for c in df.columns]
    faltantes = [col for col in requeridas if col not in columnas_df]
    
    if faltantes:
        raise ColumnaFaltanteError(faltantes, tipo_operacion)


def obtener_resumen_columnas(df: pd.DataFrame) -> Dict[str, any]:
    return {
        "total_columnas": len(df.columns),
        "columnas": list(df.columns),
        "total_filas": len(df),
        "filas_con_datos": int(df.notna().any(axis=1).sum()),
    }
