"""
═══════════════════════════════════════════════════════════════
PROCESADOR OUTBOUND (Exportaciones)
═══════════════════════════════════════════════════════════════
ORDEN DE OPERACIONES (CRÍTICO):
  1. Compatibilidad de alias de columnas
  2. Limpieza
  3. Inferir BU desde el patrón del Waybill (SEGUNDO Mxx si hay 2)
  4. 🔄 Aplicar regla Miscelaneus → crea 'BU Final'
  5. Calcular %Proporción y Calc_Exp (usando costo variable o fijo)
  6. Agrupar por 'BU Final'

REGLA DEL BU (de PRORRATEO_EXPO!C4):
  Calc_Exp = (Peso item / Peso total Waybill) × $1,500
  BU extraído del patrón del Waybill (segundo BU si hay 2)
═══════════════════════════════════════════════════════════════
"""
import pandas as pd
import numpy as np
import re
from typing import Dict, Optional
from dataclasses import dataclass, field

from src.reglas.regla_miscelaneus import (
    aplicar_regla_miscelaneus,
    cargar_config_miscelaneus,
)
from src.utils.logger import configurar_logger

logger = configurar_logger("procesar_outbound")


@dataclass
class ResultadoOutbound:
    detalle: pd.DataFrame
    resumen_bu: pd.DataFrame
    resumen_waybills: pd.DataFrame
    metricas: Dict = field(default_factory=dict)
    advertencias: list = field(default_factory=list)
    reporte_miscelaneus: Dict = field(default_factory=dict)


# ════════════════════════════════════════════════════════════
# FUNCIÓN: INFERIR BU DESDE EL WAYBILL NUMBER
# ════════════════════════════════════════════════════════════
def _inferir_bu_desde_waybill(waybill: str) -> str:
    """
    Extrae el BU del Waybill Number según la regla del negocio.
    
    Regla (de PRORRATEO_EXPO!C4):
      • Si el Waybill contiene 2 BUs → tomar el SEGUNDO
      • Si contiene 1 solo BU → tomarlo directo
      • Si no encuentra BU → devolver 'SIN_BU'
    
    Examples:
      'FG-R-2209LE26.M46/M45'  → 'M45'  (2 BUs → toma el 2°)
      'FG-R-2215LE26.M01/M45'  → 'M45'  (2 BUs → toma el 2°)
      'FG-R-2219LE26.M19'      → 'M19'  (1 BU → tomarlo directo)
      'FG-R-2221LE26.M45'      → 'M45'  (1 BU → tomarlo directo)
      'FG-R-2216LE26.M46/M45-2'→ 'M45'  (2 BUs con sufijo → toma el 2°)
    """
    if not isinstance(waybill, str):
        return "SIN_BU"
    
    # Buscar TODOS los patrones Mxx (M seguido de 2 dígitos)
    bus_encontrados = re.findall(r'M\d{2}', waybill.upper())
    
    if len(bus_encontrados) == 0:
        return "SIN_BU"
    elif len(bus_encontrados) == 1:
        return bus_encontrados[0]
    else:
        # 🔑 Regla del negocio: tomar el SEGUNDO (índice 1)
        return bus_encontrados[1]


# ════════════════════════════════════════════════════════════
# FUNCIÓN PRINCIPAL: PROCESAR OUTBOUND
# ════════════════════════════════════════════════════════════
def procesar_outbound(
    df_outbound: pd.DataFrame,
    costo_fijo: float = 1500.0,
    df_costos: Optional[pd.DataFrame] = None,
    columna_waybill: str = "Reference",
    columna_peso: str = "Peso Bruto",
    columna_item: str = "Item",
    columna_bu: str = "BU",
) -> ResultadoOutbound:
    """
    Procesa el reporte OUTBOUND aplicando prorrateo + regla Miscelaneus.
    
    Args:
        df_outbound: DataFrame del lector tolerante
        costo_fijo: Costo default por Waybill (default $1,500)
        df_costos: DataFrame opcional con costos variables por Waybill
                   (columnas: Reference, Fix Cost)
        columna_waybill: Nombre de la columna Waybill/Reference (default 'Reference')
        columna_peso: Nombre de la columna Peso Bruto (default 'Peso Bruto')
        columna_item: Nombre de la columna Item (default 'Item')
        columna_bu: Nombre de la columna BU (default 'BU')
    """
    logger.info("=" * 60)
    logger.info("🚢 INICIANDO PROCESAMIENTO OUTBOUND")
    logger.info("=" * 60)
    
    # ─────────────────────────────────────────────────────────
    # VALIDACIÓN INICIAL
    # ─────────────────────────────────────────────────────────
    if df_outbound is None or len(df_outbound) == 0:
        raise ValueError("El DataFrame de Outbound está vacío.")
    
    df = df_outbound.copy()
    advertencias = []
    
    # ─────────────────────────────────────────────────────────
    # PASO 0: COMPATIBILIDAD DE NOMBRES DE COLUMNAS (alias legacy)
    # ─────────────────────────────────────────────────────────
    # Reference: puede venir como 'Waybill Number' (legacy)
    if columna_waybill not in df.columns and "Waybill Number" in df.columns:
        df[columna_waybill] = df["Waybill Number"]
        logger.info("   🔄 'Waybill Number' promovido a 'Reference' (alias)")
    
    # Peso: puede venir como 'Gross Weight' o 'Gross Weight (Kgs)'
    if columna_peso not in df.columns:
        for alias in ["Gross Weight", "Gross Weight (Kgs)", "Peso Bruto (Kgs)"]:
            if alias in df.columns:
                df[columna_peso] = df[alias]
                logger.info(f"   🔄 '{alias}' promovido a '{columna_peso}' (alias)")
                break
    
    # Item: puede venir con varios nombres
    if columna_item not in df.columns:
        for alias in ["Item Code", "PN", "No. Parte Prov."]:
            if alias in df.columns:
                df[columna_item] = df[alias]
                logger.info(f"   🔄 '{alias}' promovido a '{columna_item}' (alias)")
                break
    
    logger.info(f"📊 Registros recibidos: {len(df)}")
    logger.info(f"   Columnas disponibles (primeras 15): {list(df.columns)[:15]}")
    
    # ─────────────────────────────────────────────────────────
    # PASO 1: LIMPIEZA
    # ─────────────────────────────────────────────────────────
    filas_antes = len(df)
    
    # Verificar que las columnas críticas existan (BU NO es crítica — se infiere)
    columnas_criticas = [columna_waybill, columna_peso, columna_item]
    faltantes = [c for c in columnas_criticas if c not in df.columns]
    if faltantes:
        raise ValueError(
            f"Columnas críticas faltantes en Outbound: {faltantes}. "
            f"Columnas disponibles: {list(df.columns)}"
        )
    
    # Limpiar filas inválidas
    df = df.dropna(subset=[columna_waybill])
    df = df[df[columna_waybill].astype(str).str.strip() != ""]
    df[columna_peso] = pd.to_numeric(df[columna_peso], errors="coerce")
    df = df.dropna(subset=[columna_peso])
    df = df[df[columna_peso] > 0]
    
    filas_descartadas = filas_antes - len(df)
    if filas_descartadas > 0:
        msg = f"Se descartaron {filas_descartadas} filas (sin Waybill o peso inválido)"
        advertencias.append(msg)
        logger.warning(f"⚠️ {msg}")
    
    if len(df) == 0:
        raise ValueError(
            "Todos los registros de OUTBOUND fueron descartados. "
            "Verifica que las columnas Waybill, Peso Bruto e Item existan."
        )
    
    # ─────────────────────────────────────────────────────────
    # PASO 2: INFERIR BU DESDE EL WAYBILL (regla del SEGUNDO BU)
    # ─────────────────────────────────────────────────────────
    if columna_bu not in df.columns:
        logger.info("   🧠 Columna 'BU' no existe → infiriendo desde Waybill Number")
        df[columna_bu] = df[columna_waybill].apply(_inferir_bu_desde_waybill)
    else:
        # Si existe pero tiene nulos, inferir solo los faltantes
        mask_nulos = (
            df[columna_bu].isna()
            | (df[columna_bu].astype(str).str.strip() == "")
        )
        if mask_nulos.any():
            n_nulos = mask_nulos.sum()
            logger.info(f"   🧠 Infiriendo BU para {n_nulos} filas con BU vacío")
            df.loc[mask_nulos, columna_bu] = df.loc[mask_nulos, columna_waybill].apply(
                _inferir_bu_desde_waybill
            )
    
    # Fallback final: cualquier BU vacío → 'Sin Asignar'
    df[columna_bu] = df[columna_bu].fillna("Sin Asignar")
    df.loc[df[columna_bu].astype(str).str.strip() == "", columna_bu] = "Sin Asignar"
    
    bus_originales = sorted(df[columna_bu].dropna().unique().tolist())
    logger.info(f"   ✅ BUs detectados: {bus_originales}")
    
    # ─────────────────────────────────────────────────────────
    # PASO 3: APLICAR REGLA MISCELANEUS (crea 'BU Final')
    # ─────────────────────────────────────────────────────────
    logger.info("🔄 Aplicando regla Miscelaneus...")
    
    config_misc = cargar_config_miscelaneus()
    df, reporte_miscelaneus = aplicar_regla_miscelaneus(
        df,
        columna_item=columna_item,
        columna_bu_origen=columna_bu,
        columna_bu_destino="BU Final",
        palabras_sin_filtro=config_misc["palabras_sin_filtro"],
        palabras_con_filtro_guion=config_misc["palabras_con_filtro_guion"],
        bu_miscelaneus=config_misc["bu_destino"],
    )
    
    # Verificación defensiva: si la regla no creó la columna, copiarla
    if "BU Final" not in df.columns:
        logger.warning("⚠️ 'BU Final' no se creó. Copiando desde 'BU'.")
        df["BU Final"] = df[columna_bu]
    
    if reporte_miscelaneus.get("items_reasignados", 0) > 0:
        logger.info(
            f"   ✅ {reporte_miscelaneus['items_reasignados']} items reasignados a "
            f"'{reporte_miscelaneus['bu_destino']}'"
        )
    else:
        logger.info("   ℹ️ Sin items reasignados a Miscelaneus")
    
    # ─────────────────────────────────────────────────────────
    # PASO 4: APLICAR COSTOS VARIABLES (si existen)
    # ─────────────────────────────────────────────────────────
    logger.info("💰 Aplicando costos por Waybill...")
    
    # Inicializar Fix Cost con el costo fijo default
    df["Fix Cost"] = costo_fijo
    
    if df_costos is not None and len(df_costos) > 0:
        mapa_costos = dict(zip(
            df_costos["Reference"].astype(str),
            df_costos["Fix Cost"],
        ))
        
        df["Fix Cost"] = (
            df[columna_waybill]
            .astype(str)
            .map(mapa_costos)
            .fillna(costo_fijo)
        )
        
        n_variables = int((df["Fix Cost"] != costo_fijo).sum())
        logger.info(f"   ✅ {n_variables} filas con costo variable aplicado")
    else:
        logger.info(f"   ℹ️ Sin tabla de costos variables. Usando default: ${costo_fijo}")
    
    # ─────────────────────────────────────────────────────────
    # PASO 5: CALCULAR %PROPORCIÓN Y CALC_EXP
    # ─────────────────────────────────────────────────────────
    logger.info("🧮 Calculando %Proporción y Calc_Exp...")
    
    df["Peso Total Waybill"] = df.groupby(columna_waybill)[columna_peso].transform("sum")
    df["%Proporcion"] = df[columna_peso] / df["Peso Total Waybill"]
    df["%Proporcion"] = df["%Proporcion"].fillna(0)
    df["Calc_Exp"] = df["%Proporcion"] * df["Fix Cost"]
    
    # Alias para retrocompatibilidad con código antiguo / Summary
    df["Amount"] = df["Calc_Exp"]
    
    # ─────────────────────────────────────────────────────────
    # PASO 6: RESUMEN POR BU FINAL
    # ─────────────────────────────────────────────────────────
    logger.info("📊 Generando resumen por BU Final...")
    
    resumen_bu = (
        df.groupby("BU Final")
        .agg(
            **{
                "Monto Total (USD)": ("Calc_Exp", "sum"),
                "# Waybills":        (columna_waybill, "nunique"),
                "# Items":           (columna_item, "count"),
                "Peso Total (Kgs)":  (columna_peso, "sum"),
            }
        )
        .reset_index()
        .rename(columns={"BU Final": "BU"})
    )
    
    total_monto = resumen_bu["Monto Total (USD)"].sum()
    resumen_bu["%PCT"] = (
        resumen_bu["Monto Total (USD)"] / total_monto if total_monto > 0 else 0.0
    )
    resumen_bu = (
        resumen_bu
        .sort_values("Monto Total (USD)", ascending=False)
        .reset_index(drop=True)
    )
    
    # ─────────────────────────────────────────────────────────
    # PASO 7: RESUMEN POR WAYBILL
    # ─────────────────────────────────────────────────────────
    resumen_waybills = (
        df.groupby(columna_waybill)
        .agg(
            **{
                "BU Asignado": (
                    "BU Final",
                    lambda x: x.mode().iloc[0] if len(x.mode()) > 0 else "Sin Asignar"
                ),
                "# Items":          (columna_item, "count"),
                "Peso Total (Kgs)": (columna_peso, "sum"),
                "Fix Cost":         ("Fix Cost", "first"),
                "Total Amount":     ("Calc_Exp", "sum"),
            }
        )
        .reset_index()
        .rename(columns={columna_waybill: "Waybill Number"})
    )
    
    # ─────────────────────────────────────────────────────────
    # PASO 8: MÉTRICAS (con todas las claves para compatibilidad UI)
    # ─────────────────────────────────────────────────────────
    num_waybills = df[columna_waybill].nunique()
    
    # Costo esperado = suma de Fix Cost únicos por Waybill
    costo_esperado = (
        df.groupby(columna_waybill)["Fix Cost"]
        .first()
        .sum()
    )
    
    costo_calculado = df["Calc_Exp"].sum()
    diferencia = abs(costo_esperado - costo_calculado)
    
    # Detectar modo de costo (variable vs default)
    waybills_con_costo_variable = int(
        df.groupby(columna_waybill)["Fix Cost"]
        .first()
        .ne(costo_fijo)
        .sum()
    )
    
    modo_costo = "variable" if waybills_con_costo_variable > 0 else "default"
    n_waybills_variables = waybills_con_costo_variable
    
    metricas = {
        # ──── Métricas básicas ────
        "total_items":            len(df),
        "total_waybills":         num_waybills,
        "total_bus":              len(resumen_bu),
        "bus_detectados":         resumen_bu["BU"].tolist(),
        "costo_fijo_default":     costo_fijo,
        "costo_total_esperado":   round(costo_esperado, 2),
        "costo_total_calculado":  round(costo_calculado, 2),
        "diferencia_validacion":  round(diferencia, 2),
        "validacion_ok":          diferencia < 1.0,
        "filas_descartadas":      filas_descartadas,
        
        # ──── Modo costo (Outbound-only) ────
        "modo_costo":             modo_costo,
        "n_waybills_variables":   n_waybills_variables,
        "n_waybills_default":     num_waybills - n_waybills_variables,
        
        # ──── BUs especiales / nuevos ────
        "bus_especiales": [
            bu for bu in resumen_bu["BU"].tolist()
            if bu in ("Miscelaneus", "Machine", "Capex", "MCS", "Sin Asignar")
        ],
        "bus_nuevos": [],
        
        # ──── Reporte Miscelaneus ────
        "miscelaneus": {
            "items_reasignados": reporte_miscelaneus.get("items_reasignados", 0),
            "monto_reasignado":  reporte_miscelaneus.get("monto_reasignado", 0.0),
            "bus_origen":        reporte_miscelaneus.get("bus_origen_reasignados", []),
        },
    }
    
    # ─────────────────────────────────────────────────────────
    # PASO 9: LOG FINAL
    # ─────────────────────────────────────────────────────────
    logger.info("─" * 60)
    logger.info(f"✅ Items procesados:       {metricas['total_items']}")
    logger.info(f"✅ Waybills únicos:        {metricas['total_waybills']}")
    logger.info(f"✅ BUs en resumen:         {metricas['total_bus']} → {metricas['bus_detectados']}")
    logger.info(f"💰 Costo esperado:         ${metricas['costo_total_esperado']:,.2f}")
    logger.info(f"💰 Costo calculado:        ${metricas['costo_total_calculado']:,.2f}")
    logger.info(f"💵 Modo costo:             {metricas['modo_costo']}")
    logger.info(f"🔄 Items reasignados:      {metricas['miscelaneus']['items_reasignados']}")
    logger.info(f"✅ Validación OK:          {metricas['validacion_ok']}")
    logger.info("=" * 60)
    
    return ResultadoOutbound(
        detalle=df,
        resumen_bu=resumen_bu,
        resumen_waybills=resumen_waybills,
        metricas=metricas,
        advertencias=advertencias,
        reporte_miscelaneus=reporte_miscelaneus,
    )