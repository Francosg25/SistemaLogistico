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
    
    🔧 v3 — Con diagnóstico y validación de integridad:
      • Log claro de si df_costos viene cargado o vacío
      • Advertencia si la cantidad de refs en costos no cuadra con datos
      • Compatible con archivos que traen tabla embebida (EXCEL OUTBOUND.xlsx)
        y archivos sin tabla (REPORTE EXPO W19.xlsx)
    
    Returns:
        Tupla: (df_datos, df_costos)
    """
    logger.info("=" * 60)
    logger.info("📥 CARGANDO ARCHIVO OUTBOUND")
    logger.info("=" * 60)
    
    df, info = _leer_hoja_tolerante(archivo, "outbound", hoja_forzada)
    
    # ─────────────────────────────────────────────────────────
    # NORMALIZACIÓN DE COLUMNAS CRÍTICAS
    # ─────────────────────────────────────────────────────────
    df["Reference"] = normalizar_texto(df["Reference"])
    df["Peso Bruto"] = normalizar_numerico(df["Peso Bruto"])
    df["Item"] = normalizar_texto(df["Item"])
    
    if "BU" in df.columns:
        df["BU"] = normalizar_texto(df["BU"])
    else:
        df["BU"] = None
    
    # ─────────────────────────────────────────────────────────
    # COLUMNAS OPCIONALES
    # ─────────────────────────────────────────────────────────
    for col_opc in ["Customer", "Method", "Container", "Cantidad"]:
        if col_opc in df.columns:
            if col_opc == "Cantidad":
                df[col_opc] = normalizar_numerico(df[col_opc])
            else:
                df[col_opc] = normalizar_texto(df[col_opc])
    
    # ─────────────────────────────────────────────────────────
    # CREAR WAYBILL NUMBER DESDE REFERENCE SI NO EXISTE
    # ─────────────────────────────────────────────────────────
    if "Waybill Number" not in df.columns:
        df["Waybill Number"] = df["Reference"]
    
    # ─────────────────────────────────────────────────────────
    # LIMPIEZA DE FILAS INVÁLIDAS
    # ─────────────────────────────────────────────────────────
    df = eliminar_filas_vacias(df, ["Reference", "Item"])
    df = eliminar_filas_totales(df, "Reference")
    df = df[df["Peso Bruto"].notna() & (df["Peso Bruto"] > 0)]
    
    if len(df) == 0:
        raise DatosVaciosError("El archivo OUTBOUND no contiene datos válidos.")
    
    # Alias de retrocompatibilidad
    df["Gross Weight"] = df["Peso Bruto"]
    
    # ─────────────────────────────────────────────────────────
    # 🆕 CARGAR TABLA DE COSTOS VARIABLES (CON LOGGING DIAGNÓSTICO)
    # ─────────────────────────────────────────────────────────
    df_costos = _intentar_cargar_costos_outbound(archivo, info["hoja_usada"])
    
    # 🔍 CAPA 1: Logging diagnóstico para detectar bugs silenciosos
    if df_costos is None:
        logger.warning(
            "   🚨 _intentar_cargar_costos_outbound devolvió None → "
            "se usará costo default $1,500/Waybill. Esto puede ser INCORRECTO "
            "si el archivo tiene tabla de costos embebida (cols BC:BE)."
        )
    elif len(df_costos) == 0:
        logger.warning(
            "   🚨 df_costos está VACÍO (0 filas) → "
            "todos los waybills usarán default $1,500."
        )
    else:
        total_costos = df_costos["Fix Cost"].sum()
        n_refs_en_costos = df_costos["Reference"].nunique()
        logger.info(
            f"   ✅ df_costos cargado: {n_refs_en_costos} refs únicas | "
            f"Total tabla=${total_costos:,.2f}"
        )
    
    # ─────────────────────────────────────────────────────────
    # 📊 RESUMEN DE LECTURA
    # ─────────────────────────────────────────────────────────
    bus = sorted(df["BU"].dropna().unique().tolist()) if df["BU"].notna().any() else []
    logger.info(f"   ✅ BUs directos: {bus}")
    logger.info(f"   ✅ References únicas: {df['Reference'].nunique()}")
    logger.info(f"✅ OUTBOUND cargado: {len(df)} registros válidos")
    
    df.attrs["info_lectura"] = info
    
    # ─────────────────────────────────────────────────────────
    # 🆕 CAPA 3: VALIDACIÓN DE INTEGRIDAD (DENTRO de la función)
    # ─────────────────────────────────────────────────────────
    # Detecta el bug de "31 waybills × $1,500 = $46,500" antes de procesar
    n_refs_datos = df["Reference"].nunique()
    n_refs_costos = len(df_costos) if df_costos is not None else 0
    
    if n_refs_datos >= 10 and n_refs_costos < (n_refs_datos * 0.5):
        logger.warning(
            f"   ⚠️ POSIBLE BUG DETECTADO: {n_refs_datos} refs únicas en datos "
            f"pero solo {n_refs_costos} en tabla de costos. Verifica la función "
            f"_intentar_cargar_costos_outbound() — puede estar leyendo "
            f"la columna 'Reference' incorrecta (col D en vez de col BC)."
        )
    elif n_refs_costos > 0 and n_refs_datos > 0:
        cobertura = (n_refs_costos / n_refs_datos) * 100
        logger.info(
            f"   📊 Cobertura de tabla de costos: {n_refs_costos}/{n_refs_datos} "
            f"refs ({cobertura:.0f}%)"
        )
    
    return df, df_costos

def _intentar_cargar_costos_outbound(archivo, hoja: str) -> Optional[pd.DataFrame]:
    """
    🔧 v3 — FIX DEFINITIVO para columnas duplicadas (3× 'Reference')
    
    Estrategia inmune a duplicados:
      1. Lee la hoja con header=None (sin renombrar nada)
      2. Busca filas que contengan AMBOS: 'Reference' Y 'Fix Cost'
      3. Para cada 'Fix Cost', busca el 'Reference' ADYACENTE a la izquierda (máx 5 cols)
      4. Extrae datos por POSICIÓN (df.iloc[:, pos]), NO por nombre
      5. Si hay múltiples candidatos, elige el de mayor score (# refs únicas + suma)
    """
    try:
        if hasattr(archivo, "seek"):
            archivo.seek(0)
        
        # ─── Paso 1: Leer RAW (sin headers) ───
        df_raw = pd.read_excel(archivo, sheet_name=hoja, header=None, dtype=object)
        
        if len(df_raw) < 2:
            return None
        
        # ─── Paso 2: Buscar fila con 'Reference' + 'Fix Cost' ───
        fila_costos = None
        valores_fila = None
        
        for idx in range(min(20, len(df_raw))):
            row_values = df_raw.iloc[idx].tolist()
            valores_lower = [
                str(v).strip().lower() if pd.notna(v) else ""
                for v in row_values
            ]
            
            tiene_ref = any(v in ("reference", "referencia") for v in valores_lower)
            tiene_fix = any(v in ("fix cost", "fixcost") for v in valores_lower)
            
            if tiene_ref and tiene_fix:
                fila_costos = idx
                valores_fila = valores_lower
                logger.info(
                    f"   🔍 Fila con Reference+Fix Cost: idx={idx} "
                    f"(Excel row {idx + 1})"
                )
                break
        
        if fila_costos is None:
            logger.info("   ℹ️ No se encontró fila con Reference + Fix Cost")
            return None
        
        # ─── Paso 3: Localizar POSICIONES de Fix Cost y Reference adyacente ───
        pos_fix_cost_list = [
            i for i, v in enumerate(valores_fila)
            if v in ("fix cost", "fixcost")
        ]
        
        if not pos_fix_cost_list:
            return None
        
        pares_candidatos = []
        for pos_fix in pos_fix_cost_list:
            for offset in range(1, 6):  # máx 5 cols a la izquierda
                pos_candidate = pos_fix - offset
                if pos_candidate < 0:
                    break
                valor = valores_fila[pos_candidate]
                if valor in ("reference", "referencia"):
                    pares_candidatos.append((pos_candidate, pos_fix))
                    logger.info(
                        f"   📊 Par detectado: Reference@col{pos_candidate} + "
                        f"Fix Cost@col{pos_fix}"
                    )
                    break
        
        if not pares_candidatos:
            logger.info("   ℹ️ Fix Cost encontrado pero sin Reference adyacente")
            return None
        
        # ─── Paso 4: Probar cada par, elegir por score ───
        mejor_df = None
        mejor_score = 0
        
        for pos_ref, pos_fix in pares_candidatos:
            try:
                # 🔑 EXTRAER POR POSICIÓN (índice) — inmune a duplicados
                datos_ref = df_raw.iloc[fila_costos + 1:, pos_ref]
                datos_fix = df_raw.iloc[fila_costos + 1:, pos_fix]
                
                df_cand = pd.DataFrame({
                    "Reference": datos_ref.astype(str).str.strip(),
                    "Fix Cost": pd.to_numeric(datos_fix, errors="coerce"),
                })
                
                df_cand = df_cand.dropna(subset=["Fix Cost"])
                df_cand = df_cand[df_cand["Reference"] != ""]
                df_cand = df_cand[df_cand["Reference"].str.lower() != "nan"]
                df_cand = df_cand[df_cand["Fix Cost"] > 0]
                df_cand = df_cand.drop_duplicates(subset=["Reference"], keep="first")
                df_cand = df_cand.reset_index(drop=True)
                
                if len(df_cand) == 0:
                    continue
                
                n_refs = len(df_cand)
                suma = float(df_cand["Fix Cost"].sum())
                score = n_refs * 10 + (suma / 1000)
                
                logger.info(
                    f"   📊 Par (ref={pos_ref}, fix={pos_fix}): "
                    f"{n_refs} refs | Suma=${suma:,.2f} | Score={score:.0f}"
                )
                
                if score > mejor_score:
                    mejor_score = score
                    mejor_df = df_cand
            
            except Exception as e:
                logger.warning(f"   ⚠️ Par (ref={pos_ref}, fix={pos_fix}) falló: {e}")
                continue
        
        if mejor_df is None or len(mejor_df) == 0:
            return None
        
        total = float(mejor_df["Fix Cost"].sum())
        logger.info(
            f"   💰 Tabla de costos EMBEBIDA extraída: "
            f"{len(mejor_df)} refs únicas | Total: ${total:,.2f}"
        )

           # ── 🛡️ BLINDAJE FINAL: garantizar que Fix Cost tenga valores REALES ──
        # Reconfirmar tipos
        mejor_df["Fix Cost"] = pd.to_numeric(mejor_df["Fix Cost"], errors="coerce")
        mejor_df = mejor_df.dropna(subset=["Fix Cost"])
        mejor_df = mejor_df[mejor_df["Fix Cost"] > 0]
        mejor_df["Reference"] = mejor_df["Reference"].astype(str).str.strip()
        
        # Verificación crítica
        suma_final = float(mejor_df["Fix Cost"].sum())
        if suma_final <= 0:
            logger.error(
                f"   🚨 BLINDAJE ACTIVADO: Suma final = ${suma_final}. "
                f"Devolviendo None para evitar corrupción."
            )
            return None
        
        # Forzar copia profunda para evitar referencias compartidas
        mejor_df = mejor_df.reset_index(drop=True).copy(deep=True)
        
        logger.info(
            f"   ✅ Blindaje OK: {len(mejor_df)} refs | Suma=${suma_final:,.2f}"
        )
        
        return mejor_df


        return mejor_df
    
    except Exception as e:
        logger.warning(f"   ⚠️ Error cargando tabla de costos: {e}")
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
