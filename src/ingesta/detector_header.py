"""
═══════════════════════════════════════════════════════════════
DETECTOR AUTOMÁTICO DE FILA DE ENCABEZADO
═══════════════════════════════════════════════════════════════
Las hojas pueden tener el encabezado en fila 1, 3, 5, 8, etc.
Este módulo detecta automáticamente cuál fila es el encabezado
buscando la que tiene más nombres reconocibles como columnas.
═══════════════════════════════════════════════════════════════
"""
import pandas as pd
from typing import Optional, Tuple

from src.ingesta.mapeo_columnas import buscar_columna_logica
from src.utils.logger import configurar_logger

logger = configurar_logger("detector_header")


def detectar_fila_encabezado(
    archivo,
    nombre_hoja: str,
    max_filas_escanear: int = 15,
    min_columnas_reconocidas: int = 3,
) -> Tuple[Optional[int], int]:
    """
    Escanea las primeras N filas de una hoja y devuelve la fila más probable
    de ser el encabezado (la que tiene más columnas reconocibles).
    
    Args:
        archivo: Path o file-like del Excel
        nombre_hoja: Nombre de la hoja a analizar
        max_filas_escanear: Cuántas filas escanear desde arriba (default 15)
        min_columnas_reconocidas: Mínimo de columnas válidas para considerar
                                   una fila como encabezado (default 3)
    
    Returns:
        Tupla:
          - fila_header (0-indexed): índice de la fila de encabezado, o None
          - num_columnas_reconocidas: cuántas columnas válidas tiene
    """
    try:
        if hasattr(archivo, "seek"):
            archivo.seek(0)
        
        # Leer sin encabezado (para escanear manualmente)
        df_raw = pd.read_excel(
            archivo,
            sheet_name=nombre_hoja,
            header=None,
            nrows=max_filas_escanear,
            dtype=object,
        )
    except Exception as e:
        logger.warning(f"   No se pudo leer hoja '{nombre_hoja}': {e}")
        return None, 0
    
    mejor_fila = None
    mejor_score = 0
    
    for idx, fila in df_raw.iterrows():
        valores = [str(v).strip() if pd.notna(v) else "" for v in fila.values]
        
        # Saltar filas vacías o casi vacías
        no_vacias = sum(1 for v in valores if v)
        if no_vacias < min_columnas_reconocidas:
            continue
        
        # Contar cuántas columnas son reconocibles
        reconocidas = sum(
            1 for v in valores
            if v and buscar_columna_logica(v) is not None
        )
        
        if reconocidas >= min_columnas_reconocidas and reconocidas > mejor_score:
            mejor_score = reconocidas
            mejor_fila = idx
    
    if mejor_fila is not None:
        logger.info(
            f"   📐 Fila de encabezado detectada: fila {mejor_fila + 1} "
            f"({mejor_score} columnas reconocidas)"
        )
    
    return mejor_fila, mejor_score