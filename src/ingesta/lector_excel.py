"""
Lector de archivos Excel.
Implementa funciones independientes para cargar SEA, LAND y OUTBOUND.

Cada función:
1. Detecta automáticamente la fila de encabezado
2. Lee solo las columnas relevantes
3. Limpia y normaliza los datos
4. Valida columnas obligatorias
5. Retorna un DataFrame listo para procesar
"""
import pandas as pd
from pathlib import Path
from typing import Union, BinaryIO
from openpyxl import load_workbook

from src.ingesta.excepciones import (
    ArchivoInvalidoError,
    HojaNoEncontradaError,
    DatosVaciosError,
)
from src.ingesta.normalizador import (
    normalizar_texto,
    normalizar_numerico,
    eliminar_filas_vacias,
    eliminar_filas_totales,
)
from src.ingesta.validador_columnas import validar_columnas
from src.utils.logger import configurar_logger

logger = configurar_logger("ingesta")


# ============================================================
# CONFIGURACIÓN POR TIPO DE OPERACIÓN
# ============================================================
# Filas de encabezado basadas en el análisis del Excel real:
# - Outbound: fila 8
# - Sea: fila 5
# - Land: fila 5
CONFIG_HOJAS = {
    "sea": {
        "nombres_hoja": ["Sea", "SEA", "sea", "China Maritimos", "Maritimos"],
        "fila_encabezado": 5,  # En pandas: header=4 (0-indexed)
        "columnas_clave": ["BU", "Container Number", "Total Gross Weight"],
    },
    "land": {
        "nombres_hoja": ["Land", "LAND", "land", "Terrestre"],
        "fila_encabezado": 5,
        "columnas_clave": ["Reference", "BU", "Peso Bruto (Kgs)"],
    },
    "outbound": {
        "nombres_hoja": ["Outbound", "OUTBOUND", "outbound", "Exportaciones"],
        "fila_encabezado": 8,
        "columnas_clave": ["Reference", "Waybill Number", "Gross Weight"],
    },
}


# ============================================================
# FUNCIONES AUXILIARES
# ============================================================
def _detectar_hoja(archivo: Union[str, Path, BinaryIO], 
                   nombres_posibles: list) -> str:
    """
    Busca el nombre exacto de la hoja en el archivo.
    Acepta variantes de mayúsculas/minúsculas.
    """
    try:
        wb = load_workbook(archivo, read_only=True, data_only=True)
        hojas_disponibles = wb.sheetnames
        wb.close()
    except Exception as e:
        raise ArchivoInvalidoError(f"No se pudo abrir el archivo: {e}")
    
    # Búsqueda exacta primero
    for nombre in nombres_posibles:
        if nombre in hojas_disponibles:
            return nombre
    
    # Búsqueda case-insensitive
    hojas_lower = {h.lower(): h for h in hojas_disponibles}
    for nombre in nombres_posibles:
        if nombre.lower() in hojas_lower:
            return hojas_lower[nombre.lower()]
    
    raise HojaNoEncontradaError(nombres_posibles[0], hojas_disponibles)


def _detectar_fila_encabezado(archivo: Union[str, Path, BinaryIO],
                               hoja: str,
                               columnas_clave: list,
                               fila_default: int,
                               max_filas_busqueda: int = 15) -> int:
    """
    Intenta detectar automáticamente la fila de encabezado buscando
    las columnas clave. Si no las encuentra, usa la fila default.
    
    Returns:
        Número de fila (1-indexed, como Excel)
    """
    try:
        # Lee las primeras N filas sin encabezado
        df_preview = pd.read_excel(
            archivo, 
            sheet_name=hoja, 
            header=None, 
            nrows=max_filas_busqueda
        )
        
        for idx, fila in df_preview.iterrows():
            valores_fila = [str(v).strip() for v in fila.values if pd.notna(v)]
            # Si encuentra al menos 2 columnas clave en esta fila, es el encabezado
            coincidencias = sum(1 for col in columnas_clave if col in valores_fila)
            if coincidencias >= 2:
                fila_detectada = idx + 1  # 1-indexed
                logger.info(f"Encabezado detectado automáticamente en fila {fila_detectada}")
                return fila_detectada
        
        logger.warning(
            f"No se detectó encabezado automáticamente. "
            f"Usando fila default: {fila_default}"
        )
        return fila_default
    
    except Exception as e:
        logger.warning(f"Error detectando encabezado: {e}. Usando fila {fila_default}")
        return fila_default


def _leer_excel_con_header(archivo: Union[str, Path, BinaryIO],
                            hoja: str,
                            fila_encabezado: int) -> pd.DataFrame:
    """
    Lee un Excel especificando la fila de encabezado.
    pandas usa 0-indexed, Excel usa 1-indexed.
    """
    try:
        df = pd.read_excel(
            archivo,
            sheet_name=hoja,
            header=fila_encabezado - 1,  # Convertir a 0-indexed
            dtype=object,  # Lee todo como object para evitar inferencia automática
        )
        # Limpiar nombres de columnas (espacios, saltos de línea)
        df.columns = [str(c).strip() for c in df.columns]
        return df
    except Exception as e:
        raise ArchivoInvalidoError(f"Error al leer la hoja '{hoja}': {e}")


# ============================================================
# FUNCIÓN: CARGAR SEA
# ============================================================
def cargar_sea(archivo: Union[str, Path, BinaryIO]) -> pd.DataFrame:
    """
    Carga el reporte SEA (Importaciones Marítimas).
    
    Estructura esperada:
        - Hoja: 'Sea' (o variantes)
        - Encabezado: fila 5
        - Columnas clave: BU, Item Code, Container Number, Total Gross Weight
    
    Args:
        archivo: Ruta al archivo o objeto file-like (Streamlit upload)
    
    Returns:
        DataFrame normalizado y validado
    
    Raises:
        HojaNoEncontradaError, ColumnaFaltanteError, DatosVaciosError
    """
    logger.info("📥 Cargando archivo SEA...")
    config = CONFIG_HOJAS["sea"]
    
    # 1. Detectar hoja
    hoja = _detectar_hoja(archivo, config["nombres_hoja"])
    logger.info(f"   Hoja detectada: '{hoja}'")
    
    # 2. Detectar fila de encabezado
    fila_header = _detectar_fila_encabezado(
        archivo, hoja, config["columnas_clave"], config["fila_encabezado"]
    )
    
    # 3. Leer el Excel
    df = _leer_excel_con_header(archivo, hoja, fila_header)
    logger.info(f"   Filas leídas: {len(df)} | Columnas: {len(df.columns)}")
    
    # 4. Validar columnas obligatorias
    validar_columnas(df, "sea")
    
    # 5. Normalizar datos
    df["BU"] = normalizar_texto(df["BU"])
    df["Item Code"] = normalizar_texto(df["Item Code"])
    df["Container Number"] = normalizar_texto(df["Container Number"])
    df["Total Gross Weight"] = normalizar_numerico(df["Total Gross Weight"])
    
    # 6. Limpiar filas vacías y totales
    df = eliminar_filas_vacias(df, ["Container Number", "Item Code"])
    df = eliminar_filas_totales(df, "BU")
    
    # 7. Validar que haya datos
    if len(df) == 0:
        raise DatosVaciosError("El archivo SEA no contiene datos válidos.")
    
    logger.info(f"✅ SEA cargado correctamente: {len(df)} registros válidos")
    return df


# ============================================================
# FUNCIÓN: CARGAR LAND
# ============================================================
def cargar_land(archivo: Union[str, Path, BinaryIO]) -> pd.DataFrame:
    """
    Carga el reporte LAND (Importaciones Terrestres).
    
    Estructura esperada:
        - Hoja: 'land' (o variantes)
        - Encabezado: fila 5
        - Columnas clave: Reference, BU, Peso Bruto (Kgs), No. Parte Prov.
    """
    logger.info("📥 Cargando archivo LAND...")
    config = CONFIG_HOJAS["land"]
    
    hoja = _detectar_hoja(archivo, config["nombres_hoja"])
    logger.info(f"   Hoja detectada: '{hoja}'")
    
    fila_header = _detectar_fila_encabezado(
        archivo, hoja, config["columnas_clave"], config["fila_encabezado"]
    )
    
    df = _leer_excel_con_header(archivo, hoja, fila_header)
    logger.info(f"   Filas leídas: {len(df)} | Columnas: {len(df.columns)}")
    
    validar_columnas(df, "land")
    
    # Normalización
    df["Inbound/Outbound"] = normalizar_texto(df["Inbound/Outbound"])
    df["Method"] = normalizar_texto(df["Method"])
    df["Reference"] = normalizar_texto(df["Reference"])
    df["BU"] = normalizar_texto(df["BU"])
    df["Peso Bruto (Kgs)"] = normalizar_numerico(df["Peso Bruto (Kgs)"])
    df["No. Parte Prov."] = normalizar_texto(df["No. Parte Prov."])
    
    df = eliminar_filas_vacias(df, ["Reference", "No. Parte Prov."])
    df = eliminar_filas_totales(df, "Reference")
    
    if len(df) == 0:
        raise DatosVaciosError("El archivo LAND no contiene datos válidos.")
    
    logger.info(f"✅ LAND cargado correctamente: {len(df)} registros válidos")
    return df


# ============================================================
# FUNCIÓN: CARGAR OUTBOUND
# ============================================================
def cargar_outbound(archivo: Union[str, Path, BinaryIO]) -> pd.DataFrame:
    """
    Carga el reporte OUTBOUND (Exportaciones).
    
    Estructura esperada:
        - Hoja: 'Outbound' (o variantes)
        - Encabezado: fila 8
        - Columnas clave: Reference, Waybill Number, Gross Weight, Item, Qty Pzas
    """
    logger.info("📥 Cargando archivo OUTBOUND...")
    config = CONFIG_HOJAS["outbound"]
    
    hoja = _detectar_hoja(archivo, config["nombres_hoja"])
    logger.info(f"   Hoja detectada: '{hoja}'")
    
    fila_header = _detectar_fila_encabezado(
        archivo, hoja, config["columnas_clave"], config["fila_encabezado"]
    )
    
    df = _leer_excel_con_header(archivo, hoja, fila_header)
    logger.info(f"   Filas leídas: {len(df)} | Columnas: {len(df.columns)}")
    
    validar_columnas(df, "outbound")
    
    # Normalización
    df["Inbound/Outbound"] = normalizar_texto(df["Inbound/Outbound"])
    df["Method"] = normalizar_texto(df["Method"])
    df["Reference"] = normalizar_texto(df["Reference"])
    df["BU"] = normalizar_texto(df["BU"])
    df["Gross Weight"] = normalizar_numerico(df["Gross Weight"])
    df["Waybill Number"] = normalizar_texto(df["Waybill Number"])
    df["Item"] = normalizar_texto(df["Item"])
    df["Qty Pzas"] = normalizar_numerico(df["Qty Pzas"])
    
    # Columnas opcionales (si existen)
    if "Customer" in df.columns:
        df["Customer"] = normalizar_texto(df["Customer"])
    if "ADDRESS" in df.columns:
        df["ADDRESS"] = normalizar_texto(df["ADDRESS"])
    
    df = eliminar_filas_vacias(df, ["Reference", "Item"])
    df = eliminar_filas_totales(df, "Reference")
    
    if len(df) == 0:
        raise DatosVaciosError("El archivo OUTBOUND no contiene datos válidos.")
    
    logger.info(f"✅ OUTBOUND cargado correctamente: {len(df)} registros válidos")
    return df



def obtener_metadata(archivo: Union[str, Path, BinaryIO]) -> dict:
    """
    Retorna información general del archivo Excel sin cargarlo completo.
    Útil para mostrar al usuario antes de procesar.
    """
    try:
        wb = load_workbook(archivo, read_only=True, data_only=True)
        metadata = {
            "hojas": wb.sheetnames,
            "total_hojas": len(wb.sheetnames),
        }
        wb.close()
        return metadata
    except Exception as e:
        raise ArchivoInvalidoError(f"No se pudo leer metadata: {e}")