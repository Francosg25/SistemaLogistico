"""
Normalizador de datos.
Limpia espacios, convierte tipos, maneja nulos y estandariza valores.
"""
import pandas as pd
import numpy as np
from typing import List


def normalizar_texto(serie: pd.Series) -> pd.Series:
    """Limpia espacios, convierte a string y maneja nulos en columnas de texto."""
    return (
        serie.astype(str)
        .str.strip()
        .replace({"nan": np.nan, "None": np.nan, "": np.nan})
    )


def normalizar_numerico(serie: pd.Series) -> pd.Series:
    """
    Convierte a numérico, manejando formatos con comas y espacios.
    Ejemplo: '1,500.00' → 1500.00
    """
    if serie.dtype in ["int64", "float64"]:
        return serie
    
    serie_limpia = (
        serie.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace(" ", "", regex=False)
        .str.strip()
    )
    return pd.to_numeric(serie_limpia, errors="coerce")


def eliminar_filas_vacias(df: pd.DataFrame, columnas_clave: List[str]) -> pd.DataFrame:
    """Elimina filas donde TODAS las columnas clave están vacías."""
    return df.dropna(subset=columnas_clave, how="all").reset_index(drop=True)


def eliminar_filas_totales(df: pd.DataFrame, columna_referencia: str) -> pd.DataFrame:
    """
    Elimina filas que contienen totales o subtotales (texto como 'Total', 'TOTAL').
    """
    if columna_referencia not in df.columns:
        return df
    
    mask = ~df[columna_referencia].astype(str).str.upper().str.contains(
        "TOTAL|SUBTOTAL|GRAN TOTAL", 
        na=False, 
        regex=True
    )
    return df[mask].reset_index(drop=True)
