"""
═══════════════════════════════════════════════════════════════
PROCESADOR OUTBOUND v6.3 — Detección robusta de BU + Waybill
═══════════════════════════════════════════════════════════════
🎯 Fórmula Excel BP9: =BO9/SUMIFS($BO:$BO,$BI:$BI,BI9)
🎯 Fórmula Excel BQ9: =XLOOKUP(BI9,$BC:$BC,$BE:$BE)*BP9

Cambios v6.3:
  • Detección de BU usa Waybill Number (col G) si existe, NO Reference (col D)
  • Si el Excel YA tiene la columna BU llena → respetarla (no sobreescribir)
  • Logger más verboso para debugging
═══════════════════════════════════════════════════════════════
"""
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import re
import pandas as pd
import numpy as np

# 🔧 Imports tolerantes
try:
    from src.reglas.regla_miscelaneus import aplicar_regla_miscelaneus
except ImportError:
    def aplicar_regla_miscelaneus(df, columna_item="Item", **kwargs):
        return df, 0

try:
    from src.utils.logger import configurar_logger
    logger = configurar_logger("procesar_outbound")
except ImportError:
    import logging
    logger = logging.getLogger("procesar_outbound")
    logger.setLevel(logging.INFO)


# ════════════════════════════════════════════════════════════
# DETECTOR DE BU EMBEBIDO
# ════════════════════════════════════════════════════════════
PATRONES_BU_VALIDOS = ["M01", "M19", "M23", "M45", "M46", "M00"]


def _detectar_bu_de_waybill(waybill: str) -> Optional[str]:
    """
    Detecta el BU desde el patrón del Waybill.
    Si hay 2 BUs (ej. M01/M45 o M46-M45), toma el SEGUNDO.
    
    Soporta separadores: . / - _ y combinaciones.
    """
    if not waybill or pd.isna(waybill):
        return None

    txt = str(waybill).upper()
    # Buscar M## como patrón delimitado (acepta . / - _ como separadores)
    matches = re.findall(r"M\d{2}", txt)

    if not matches:
        return None

    matches_validos = [m for m in matches if m in PATRONES_BU_VALIDOS]

    if not matches_validos:
        return None

    if len(matches_validos) >= 2:
        return matches_validos[1]  # segundo BU si hay 2

    return matches_validos[0]


def _detectar_bu_de_item(item: str) -> Optional[str]:
    """Detecta BU desde el prefijo del Item Code."""
    if not item or pd.isna(item):
        return None

    txt = str(item).strip()

    if txt.startswith("1651-"):
        return "M46"
    if txt.startswith("1908-"):
        return "M23"

    return None


def detectar_bu_outbound(waybill: str, item: str = "") -> Optional[str]:
    """Cascada de detección: Waybill → Item Code → None."""
    bu = _detectar_bu_de_waybill(waybill)
    if bu:
        return bu

    bu = _detectar_bu_de_item(item)
    if bu:
        return bu

    return None


# ════════════════════════════════════════════════════════════
# 🛡️ NORMALIZADOR DEL RESULTADO DE aplicar_regla_miscelaneus
# ════════════════════════════════════════════════════════════
def _normalizar_resultado_misc(resultado: Any, df_original: pd.DataFrame) -> tuple:
    """Acepta cualquier formato y devuelve (df, n_misc:int)."""
    if isinstance(resultado, tuple) and len(resultado) == 2:
        df_res, info = resultado

        if not isinstance(df_res, pd.DataFrame):
            logger.warning(f"   ⚠️ Primer elemento no es DataFrame: {type(df_res)}")
            df_res = df_original

        if isinstance(info, dict):
            n = (
                info.get("reasignados")
                or info.get("n_reasignados")
                or info.get("items_reasignados")
                or info.get("count")
                or info.get("total")
                or info.get("n")
                or 0
            )
            if not n:
                for v in info.values():
                    if isinstance(v, (list, tuple, set)):
                        n = len(v)
                        break
            return df_res, int(n) if n else 0

        if isinstance(info, (list, tuple, set)):
            return df_res, len(info)

        if isinstance(info, (int, float)):
            return df_res, int(info)

        if info is None:
            return df_res, 0

        logger.warning(f"   ⚠️ Tipo inesperado: {type(info)}")
        return df_res, 0

    if isinstance(resultado, pd.DataFrame):
        return resultado, 0

    logger.warning(f"   ⚠️ Formato inesperado: {type(resultado)}")
    return df_original, 0


# ════════════════════════════════════════════════════════════
# RESULTADO
# ════════════════════════════════════════════════════════════
@dataclass
class ResultadoOutbound:
    df_detalle: pd.DataFrame
    resumen_bu: pd.DataFrame
    resumen_waybills: pd.DataFrame
    metricas: Dict[str, Any] = field(default_factory=dict)


# ════════════════════════════════════════════════════════════
# 🎯 FUNCIÓN PRINCIPAL
# ════════════════════════════════════════════════════════════
def procesar_outbound(
    df_outbound: pd.DataFrame,
    costo_fijo: float = 1500.0,
    df_costos: Optional[pd.DataFrame] = None,
    columna_waybill: str = "Waybill Number",  # 🆕 v6.3: default cambiado a Waybill Number
    columna_peso: str = "Peso Bruto",
    columna_item: str = "Item",
    tolerancia: float = 0.01,
) -> ResultadoOutbound:
    """
    Procesa OUTBOUND aplicando fórmulas idénticas al Excel original.
    
    🆕 v6.3: 
      • Por DEFAULT agrupa por 'Waybill Number' (no por 'Reference')
      • Si el DataFrame ya tiene columna 'BU' llena, la respeta
      • Detección de BU desde Waybill ahora soporta . / - _ como separadores
    """
    logger.info("=" * 60)
    logger.info("🚢 PROCESANDO OUTBOUND v6.3")
    logger.info("=" * 60)

    df = df_outbound.copy()
    
    # 🆕 Detectar la mejor columna de "grupo": Waybill Number → Reference como fallback
    columna_grupo = _detectar_columna_grupo(df, columna_waybill)
    logger.info(f"   📍 Columna grupo: '{columna_grupo}'")
    
    df = _normalizar_alias(df, columna_grupo, columna_peso, columna_item)

    # 1. INFERIR BU (solo si NO está ya asignado en la columna BU)
    if "BU" not in df.columns:
        df["BU"] = None
    
    # Contar cuántos BUs ya vienen del Excel
    n_bus_originales = df["BU"].notna().sum()
    logger.info(f"   📊 BUs originales del Excel: {n_bus_originales}/{len(df)}")
    
    # Solo inferir donde NO hay BU
    mask_sin_bu = df["BU"].isna() | (df["BU"].astype(str).str.strip() == "")
    df.loc[mask_sin_bu, "BU"] = df.loc[mask_sin_bu].apply(
        lambda r: detectar_bu_outbound(
            r.get(columna_grupo, ""),
            r.get(columna_item, "")
        ),
        axis=1,
    )
    
    bus_detectados = sorted(df["BU"].dropna().unique().tolist())
    n_bus_finales = df["BU"].notna().sum()
    n_inferidos = n_bus_finales - n_bus_originales
    logger.info(f"   ✅ BUs detectados: {bus_detectados}")
    logger.info(f"   🔍 Inferidos por cascada: {n_inferidos}")
    logger.info(f"   ❌ Sin BU asignable: {len(df) - n_bus_finales}")

    # 2. Regla Miscelaneus
    resultado_misc = aplicar_regla_miscelaneus(df, columna_item=columna_item)
    df, n_misc = _normalizar_resultado_misc(resultado_misc, df)
    df["BU Final"] = df["BU"]
    if n_misc:
        logger.info(f"   🔄 Reasignados a Miscelaneus: {n_misc}")

    # 3. Asignar Fix Cost
    df["Fix Cost"] = _asignar_fix_cost(df, costo_fijo, df_costos, columna_grupo)

    # 4. Calcular %Proportion y Calc_Exp — réplica EXACTA del Excel
    df["Peso Total Waybill"] = df.groupby(columna_grupo)[columna_peso].transform("sum")
    df["%Proportion"] = np.where(
        df["Peso Total Waybill"] > 0,
        df[columna_peso] / df["Peso Total Waybill"],
        0.0
    )
    df["Calc_Exp"] = df["%Proportion"] * df["Fix Cost"]

    # 5. RESUMEN POR BU FINAL
    resumen_bu = (
        df.groupby("BU Final", as_index=False, dropna=False)
        .agg(
            **{
                "Log. Exp": ("Calc_Exp", "sum"),
                "# Items": (columna_item, "count"),
                "# Waybills": (columna_grupo, "nunique"),
                "Peso Total (Kgs)": (columna_peso, "sum"),
            }
        )
        .rename(columns={"BU Final": "BU"})
    )
    total_amount = resumen_bu["Log. Exp"].sum()
    resumen_bu["%PCT"] = resumen_bu["Log. Exp"] / total_amount if total_amount else 0

    fila_total = pd.DataFrame([{
        "BU": "Total",
        "Log. Exp": total_amount,
        "# Items": resumen_bu["# Items"].sum(),
        "# Waybills": resumen_bu["# Waybills"].sum(),
        "Peso Total (Kgs)": resumen_bu["Peso Total (Kgs)"].sum(),
        "%PCT": 1.0,
    }])
    resumen_bu = pd.concat([resumen_bu, fila_total], ignore_index=True)

    # 6. RESUMEN POR WAYBILL
    resumen_waybills = (
        df.groupby(columna_grupo, as_index=False)
        .agg(
            **{
                "BU Asignado": ("BU Final", lambda x: x.mode().iat[0] if len(x.dropna()) else "—"),
                "# Items": (columna_item, "count"),
                "Peso Total (Kgs)": (columna_peso, "sum"),
                "Fix Cost": ("Fix Cost", "first"),
                "Total Amount": ("Calc_Exp", "sum"),
            }
        )
        .rename(columns={columna_grupo: "Waybill Number"})
    )
    resumen_waybills["Diferencia"] = (
        resumen_waybills["Total Amount"] - resumen_waybills["Fix Cost"]
    )
    resumen_waybills["Validación"] = resumen_waybills["Diferencia"].abs().apply(
        lambda d: "🟢 OK" if d <= tolerancia else "🔴 Descuadre"
    )

    # 7. MÉTRICAS
    grupos_desc = int((resumen_waybills["Diferencia"].abs() > tolerancia).sum())
    costo_esperado = float(resumen_waybills["Fix Cost"].sum())
    costo_calculado = float(df["Calc_Exp"].sum())
    validacion_ok = bool(abs(costo_esperado - costo_calculado) <= tolerancia and grupos_desc == 0)

    metricas = {
        "total_items": int(len(df)),
        "total_waybills": int(df[columna_grupo].nunique()),
        "bus_detectados": sorted(df["BU Final"].dropna().unique().tolist()),
        "costo_esperado": costo_esperado,
        "costo_total_calculado": costo_calculado,
        "modo_costo": "variable" if df_costos is not None and len(df_costos) > 0 else "default",
        "tolerancia": float(tolerancia),
        "grupos_descuadrados": grupos_desc,
        "items_reasignados_misc": int(n_misc),
        "validacion_ok": validacion_ok,
        "columna_grupo_usada": columna_grupo,  # 🆕 para debugging
    }

    logger.info("─" * 60)
    logger.info(f"✅ Items procesados: {metricas['total_items']}")
    logger.info(f"✅ Waybills únicos:  {metricas['total_waybills']}")
    logger.info(f"✅ BUs:              {metricas['bus_detectados']}")
    logger.info(f"💰 Costo total:      ${metricas['costo_total_calculado']:,.2f}")
    logger.info(f"💵 Modo:             {metricas['modo_costo']}")
    logger.info(f"✅ Validación OK:    {metricas['validacion_ok']}")
    logger.info("=" * 60)

    return ResultadoOutbound(
        df_detalle=df,
        resumen_bu=resumen_bu,
        resumen_waybills=resumen_waybills,
        metricas=metricas,
    )


# ════════════════════════════════════════════════════════════
# AUXILIARES
# ════════════════════════════════════════════════════════════
def _detectar_columna_grupo(df: pd.DataFrame, preferida: str) -> str:
    """
    🆕 v6.3: Detecta la mejor columna para agrupar.
    Prioridad: Waybill Number → Waybill → Reference (fallback)
    """
    candidatos = [preferida, "Waybill Number", "Waybill", "Reference"]
    for c in candidatos:
        if c in df.columns and df[c].notna().any():
            return c
    # Último recurso
    return df.columns[0]


def _normalizar_alias(
    df: pd.DataFrame, col_waybill: str, col_peso: str, col_item: str
) -> pd.DataFrame:
    """Garantiza que las columnas requeridas existan (con fallbacks)."""
    df = df.copy()
    if col_waybill not in df.columns:
        for alt in ["Waybill Number", "Waybill", "Reference"]:
            if alt in df.columns:
                df[col_waybill] = df[alt]
                logger.info(f"   🔄 '{alt}' usado como '{col_waybill}'")
                break
    if col_peso not in df.columns:
        for alt in ["Gross Weight", "Gross Weight (Kgs)", "Peso Bruto (Kgs)"]:
            if alt in df.columns:
                df[col_peso] = df[alt]
                break
    if col_item not in df.columns:
        for alt in ["Item Code", "Part Number", "No. Parte Prov."]:
            if alt in df.columns:
                df[col_item] = df[alt]
                break
    return df


def _asignar_fix_cost(
    df: pd.DataFrame,
    costo_default: float,
    df_costos: Optional[pd.DataFrame],
    columna_waybill: str,
) -> pd.Series:
    """Replica XLOOKUP(BI, $BC:$BC, $BE:$BE) con fallback al default."""
    if df_costos is None or len(df_costos) == 0:
        logger.info(f"   ℹ️ Sin tabla variable → tarifa fija ${costo_default:,.2f}")
        return pd.Series(costo_default, index=df.index, dtype=float)

    df_c = df_costos.copy()

    col_ref_costos = next(
        (c for c in df_c.columns if str(c).strip().lower() in ("reference", "waybill", "waybill number")),
        df_c.columns[0]
    )
    col_costo = next(
        (c for c in df_c.columns if "cost" in str(c).lower() or "tarifa" in str(c).lower() or "fix" in str(c).lower()),
        df_c.columns[1] if len(df_c.columns) > 1 else df_c.columns[0]
    )

    df_c[col_ref_costos] = df_c[col_ref_costos].astype(str).str.strip()
    waybills_norm = df[columna_waybill].astype(str).str.strip()

    mapa = dict(zip(df_c[col_ref_costos], pd.to_numeric(df_c[col_costo], errors="coerce")))
    fix_cost = waybills_norm.map(mapa).fillna(costo_default)

    n_match = int(waybills_norm.isin(mapa.keys()).sum())
    logger.info(f"   ✅ XLOOKUP: {n_match}/{len(df)} items con tarifa variable")

    return fix_cost.astype(float)