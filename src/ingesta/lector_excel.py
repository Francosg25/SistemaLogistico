"""
═══════════════════════════════════════════════════════════════
LECTOR DE ARCHIVOS EXCEL — VERSIÓN TOLERANTE
═══════════════════════════════════════════════════════════════
🔧 CAMBIO MAYOR: Ya NO usa posiciones fijas de columna (BX, CC).
   Ahora detecta:
     1. La hoja correcta por contenido
     2. La fila de encabezado automáticamente
     3. Las columnas por NOMBRE con sistema de alias
═══════════════════════════════════════════════════════════════
"""
import pandas as pd
from typing import Union, BinaryIO, Optional, Tuple
from pathlib import Path

from src.ingesta.excepciones import (
    ArchivoInvalidoError,
    HojaNoEncontradaError,
    ColumnaFaltanteError,
    DatosVaciosError,
)
from src.ingesta.normalizador import (
    normalizar_texto,
    normalizar_numerico,
    eliminar_filas_vacias,
    eliminar_filas_totales,
)
from src.ingesta.detector_hojas import detectar_hoja_optima, listar_hojas
from src.ingesta.mapeo_columnas import (
    mapear_columnas_dataframe,
    validar_columnas_criticas,
)
from src.utils.logger import configurar_logger

logger = configurar_logger("ingesta")


# ============================================================
# FUNCIÓN AUXILIAR DE LECTURA TOLERANTE
# ============================================================
def _leer_hoja_tolerante(
    archivo,
    operacion: str,
    hoja_forzada: Optional[str] = None,
) -> Tuple[pd.DataFrame, dict]:
    """
    Lee una hoja del archivo de forma tolerante a:
      - Nombres de hoja distintos
      - Fila de encabezado variable
      - Nombres de columna con alias
    
    Args:
        archivo: Path o file-like
        operacion: 'land', 'outbound' o 'sea'
        hoja_forzada: Si se proporciona, fuerza el uso de esa hoja
                       (útil para fallback con dropdown)
    
    Returns:
        Tupla: (df, info_lectura)
            df: DataFrame con columnas LÓGICAS
            info_lectura: dict con metadata (hoja usada, fila header, etc.)
    """
    # 1. Detectar hoja óptima (o usar la forzada)
    if hoja_forzada:
        from src.ingesta.detector_hojas import analizar_hoja
        mejor_hoja = analizar_hoja(archivo, hoja_forzada, operacion)
        todas = [mejor_hoja]
        if mejor_hoja["ignorada"] or mejor_hoja["score"] < 10:
            raise HojaNoEncontradaError(
                hoja_forzada,
                [h["hoja"] for h in todas],
            )
    else:
        mejor_hoja, todas = detectar_hoja_optima(archivo, operacion)
        if mejor_hoja is None:
            hojas_disponibles = [h["hoja"] for h in todas]
            raise HojaNoEncontradaError(
                f"Ninguna hoja válida para '{operacion}'",
                hojas_disponibles,
            )
    
    # 2. Leer la hoja con el encabezado detectado
    if hasattr(archivo, "seek"):
        archivo.seek(0)
    
    df = pd.read_excel(
        archivo,
        sheet_name=mejor_hoja["hoja"],
        header=mejor_hoja["fila_header"],
        dtype=object,
    )
    df.columns = [str(c).strip() for c in df.columns]
    
    logger.info(f"📥 Filas leídas: {len(df)} | Columnas: {len(df.columns)}")
    
    # 3. Mapear columnas con alias
    df, mapeo, no_mapeadas = mapear_columnas_dataframe(df, operacion)
    
    # 4. Validar columnas críticas
    es_valido, faltantes_crit, faltantes_opt = validar_columnas_criticas(df, operacion)
    
    if not es_valido:
        raise ColumnaFaltanteError(faltantes_crit, operacion)
    
    if faltantes_opt:
        logger.warning(f"   ⚠️ Columnas opcionales faltantes: {faltantes_opt}")
    
    info_lectura = {
        "hoja_usada": mejor_hoja["hoja"],
        "fila_header": mejor_hoja["fila_header"] + 1,
        "columnas_mapeadas": mapeo,
        "columnas_no_mapeadas": no_mapeadas,
        "columnas_criticas_faltantes": faltantes_crit,
        "columnas_opcionales_faltantes": faltantes_opt,
        "filas_leidas": len(df),
        "score_hoja": mejor_hoja["score"],
        "todas_las_hojas": todas,
    }
    
    return df, info_lectura


# ============================================================
# CARGAR LAND (versión tolerante)
# ============================================================
def cargar_land(archivo, hoja_forzada: Optional[str] = None) -> pd.DataFrame:
    """
    Carga el reporte LAND con detección automática de hoja y columnas.
    
    Args:
        archivo: Archivo Excel
        hoja_forzada: Opcional - si el usuario eligió una hoja manualmente
    """
    logger.info("=" * 60)
    logger.info("📥 CARGANDO ARCHIVO LAND")
    logger.info("=" * 60)
    
    df, info = _leer_hoja_tolerante(archivo, "land", hoja_forzada)
    
    # Normalización de columnas LÓGICAS
    df["Reference"] = normalizar_texto(df["Reference"])
    df["Peso Bruto"] = normalizar_numerico(df["Peso Bruto"])
    df["Item"] = normalizar_texto(df["Item"])
    
    # BU es opcional (puede no existir)
    if "BU" in df.columns:
        df["BU"] = normalizar_texto(df["BU"])
    else:
        df["BU"] = None  # Se inferirá del Reference
        logger.info("   ℹ️ Columna BU no encontrada - se inferirá del Reference")
    
    # Columnas opcionales
    for col_opc in ["Caja", "Method", "Cantidad", "Customer"]:
        if col_opc in df.columns:
            if col_opc == "Cantidad":
                df[col_opc] = normalizar_numerico(df[col_opc])
            else:
                df[col_opc] = normalizar_texto(df[col_opc])
    
    # Limpieza
    df = eliminar_filas_vacias(df, ["Reference", "Item"])
    df = eliminar_filas_totales(df, "Reference")
    
    # Filtrar pesos válidos
    df = df[df["Peso Bruto"].notna() & (df["Peso Bruto"] > 0)]
    
    if len(df) == 0:
        raise DatosVaciosError("El archivo LAND no contiene datos válidos después de limpieza.")
    
    # 🆕 ALIAS de retrocompatibilidad para no romper código existente
    df["Peso Bruto (Kgs)"] = df["Peso Bruto"]
    df["No. Parte Prov."] = df["Item"]
    
    # Log final
    bus = sorted(df["BU"].dropna().unique().tolist()) if df["BU"].notna().any() else []
    logger.info(f"   ✅ BUs detectados (directos): {bus}")
    logger.info(f"   ✅ References únicas: {df['Reference'].nunique()}")
    logger.info(f"✅ LAND cargado: {len(df)} registros válidos")
    
    # Guardar info de lectura en el DataFrame (atributo)
    df.attrs["info_lectura"] = info
    
    return df


# ============================================================
# CARGAR OUTBOUND (versión tolerante)
# ============================================================
def cargar_outbound(
    archivo,
    hoja_forzada: Optional[str] = None,
) -> Tuple[pd.DataFrame, Optional[pd.DataFrame]]:
    """
    Carga el reporte OUTBOUND y opcionalmente la tabla de costos variables.
    
    Returns:
        Tupla: (df_datos, df_costos)
    """
    logger.info("=" * 60)
    logger.info("📥 CARGANDO ARCHIVO OUTBOUND")
    logger.info("=" * 60)
    
    df, info = _leer_hoja_tolerante(archivo, "outbound", hoja_forzada)
    
    # Normalización
    df["Reference"] = normalizar_texto(df["Reference"])
    df["Peso Bruto"] = normalizar_numerico(df["Peso Bruto"])
    df["Item"] = normalizar_texto(df["Item"])
    
    if "BU" in df.columns:
        df["BU"] = normalizar_texto(df["BU"])
    else:
        df["BU"] = None
    
    for col_opc in ["Customer", "Method", "Container", "Cantidad"]:
        if col_opc in df.columns:
            if col_opc == "Cantidad":
                df[col_opc] = normalizar_numerico(df[col_opc])
            else:
                df[col_opc] = normalizar_texto(df[col_opc])
    
    # Crear Waybill desde Reference si no existe
    if "Waybill Number" not in df.columns:
        df["Waybill Number"] = df["Reference"]
    
    df = eliminar_filas_vacias(df, ["Reference", "Item"])
    df = eliminar_filas_totales(df, "Reference")
    df = df[df["Peso Bruto"].notna() & (df["Peso Bruto"] > 0)]
    
    if len(df) == 0:
        raise DatosVaciosError("El archivo OUTBOUND no contiene datos válidos.")
    
    # Alias de retrocompatibilidad
    df["Gross Weight"] = df["Peso Bruto"]
    
    # Cargar tabla de costos variables (opcional)
    df_costos = _intentar_cargar_costos_outbound(archivo, info["hoja_usada"])
    
    if df_costos is not None and len(df_costos) > 0:
        logger.info(f"   💰 Tabla de costos cargada: {len(df_costos)} references")
    
    bus = sorted(df["BU"].dropna().unique().tolist()) if df["BU"].notna().any() else []
    logger.info(f"   ✅ BUs directos: {bus}")
    logger.info(f"   ✅ References únicas: {df['Reference'].nunique()}")
    logger.info(f"✅ OUTBOUND cargado: {len(df)} registros válidos")
    
    df.attrs["info_lectura"] = info
    return df, df_costos


def _intentar_cargar_costos_outbound(archivo, hoja: str) -> Optional[pd.DataFrame]:
    """Intenta cargar tabla de costos variables. Si no existe, devuelve None."""
    try:
        if hasattr(archivo, "seek"):
            archivo.seek(0)
        
        # Buscar columnas que contengan "Cost" o "Fix Cost"
        df_raw = pd.read_excel(archivo, sheet_name=hoja, header=None, nrows=20, dtype=object)
        
        # Escanear todas las celdas buscando "Reference" + "Fix Cost"
        fila_costos = None
        for idx, row in df_raw.iterrows():
            valores = [str(v).strip().lower() if pd.notna(v) else "" for v in row.values]
            tiene_ref = any("reference" in v or "referencia" in v for v in valores)
            tiene_fix = any("fix cost" in v or "fixcost" in v for v in valores)
            if tiene_ref and tiene_fix:
                fila_costos = idx
                break
        
        if fila_costos is None:
            return None
        
        # Releer con ese header
        if hasattr(archivo, "seek"):
            archivo.seek(0)
        df_full = pd.read_excel(archivo, sheet_name=hoja, header=fila_costos, dtype=object)
        df_full.columns = [str(c).strip() for c in df_full.columns]
        
        # Buscar las columnas relevantes
        col_ref = None
        col_cost = None
        col_fix = None
        for col in df_full.columns:
            col_lower = col.lower()
            if "reference" in col_lower and col_ref is None:
                col_ref = col
            elif col_lower in ("cost (usd)", "cost", "costo (usd)"):
                col_cost = col
            elif "fix cost" in col_lower or "fixcost" in col_lower:
                col_fix = col
        
        if not col_ref or not col_fix:
            return None
        
        df_costos = df_full[[col_ref, col_cost, col_fix] if col_cost else [col_ref, col_fix]].copy()
        df_costos.columns = ["Reference", "Cost (USD)", "Fix Cost"] if col_cost else ["Reference", "Fix Cost"]
        
        df_costos["Reference"] = normalizar_texto(df_costos["Reference"])
        df_costos["Fix Cost"] = normalizar_numerico(df_costos["Fix Cost"])
        if "Cost (USD)" in df_costos.columns:
            df_costos["Cost (USD)"] = normalizar_numerico(df_costos["Cost (USD)"])
        
        df_costos = df_costos.dropna(subset=["Reference", "Fix Cost"])
        df_costos = df_costos[df_costos["Fix Cost"] > 0]
        df_costos = df_costos.reset_index(drop=True)
        
        return df_costos if len(df_costos) > 0 else None
    
    except Exception as e:
        logger.debug(f"   No se pudo cargar tabla de costos: {e}")
        return None


# ============================================================
# CARGAR SEA (versión tolerante)
# ============================================================
def cargar_sea(archivo, hoja_forzada: Optional[str] = None) -> pd.DataFrame:
    """Carga el reporte SEA con detección automática."""
    logger.info("=" * 60)
    logger.info("📥 CARGANDO ARCHIVO SEA")
    logger.info("=" * 60)
    
    df, info = _leer_hoja_tolerante(archivo, "sea", hoja_forzada)
    
    df["Container"] = normalizar_texto(df["Container"])
    df["Peso Bruto"] = normalizar_numerico(df["Peso Bruto"])
    df["Item"] = normalizar_texto(df["Item"])
    
    if "BU" in df.columns:
        df["BU"] = normalizar_texto(df["BU"])
    else:
        df["BU"] = None
    
    for col_opc in ["Subinventory", "Costo"]:
        if col_opc in df.columns:
            if col_opc == "Costo":
                df[col_opc] = normalizar_numerico(df[col_opc])
            else:
                df[col_opc] = normalizar_texto(df[col_opc])
    
    df = eliminar_filas_vacias(df, ["Container", "Item"])
    df = eliminar_filas_totales(df, "Container")
    df = df[df["Peso Bruto"].notna() & (df["Peso Bruto"] > 0)]
    
    if len(df) == 0:
        raise DatosVaciosError("El archivo SEA no contiene datos válidos.")
    
    # Alias retrocompatibilidad
    df["Container Number"] = df["Container"]
    df["Item Code"] = df["Item"]
    df["Total Gross Weight"] = df["Peso Bruto"]
    
    bus = sorted(df["BU"].dropna().unique().tolist()) if df["BU"].notna().any() else []
    logger.info(f"   ✅ BUs: {bus}")
    logger.info(f"✅ SEA cargado: {len(df)} registros válidos")
    
    df.attrs["info_lectura"] = info
    return df


# ============================================================
# METADATA
# ============================================================
def obtener_metadata(archivo) -> dict:
    """Retorna información general del archivo Excel."""
    hojas = listar_hojas(archivo)
    return {
        "hojas": hojas,
        "total_hojas": len(hojas),
    }
