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

🔧 v4 — Fix del bug $0.00:
  • Usa __costo_aplicado__ como columna intermedia (nombre único)
  • Evita colisión con 'Fix Cost' que el mapeador renombra a 'Costo_2'
  • Garantiza astype(float) y conversión explícita
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
# FUNCIÓN AUX: INFERIR BU DESDE EL WAYBILL NUMBER
# ════════════════════════════════════════════════════════════
def _inferir_bu_desde_waybill(waybill: str) -> str:
    """
    Extrae el BU del Waybill Number según la regla del negocio.
    
    Regla (de PRORRATEO_EXPO!C4):
      • 2 BUs → tomar el SEGUNDO
      • 1 BU → tomarlo directo
      • Sin BU → 'SIN_BU'
    """
    if not isinstance(waybill, str):
        return "SIN_BU"
    
    bus_encontrados = re.findall(r'M\d{2}', waybill.upper())
    
    if len(bus_encontrados) == 0:
        return "SIN_BU"
    elif len(bus_encontrados) == 1:
        return bus_encontrados[0]
    else:
        return bus_encontrados[1]


# ════════════════════════════════════════════════════════════
# FUNCIÓN AUX: EXTRAER REFERENCE BASE
# ════════════════════════════════════════════════════════════
def _extraer_reference_base(ref) -> str:
    """
    Quita sufijos de una Reference para hacer matching.
    
    Examples:
      'FG-R-2209LE26.M46/M45'  → 'FG-R-2209LE26'
      'FG-R-2221LE26.M45'      → 'FG-R-2221LE26'
      'FG-R-2216LE26.M46/M45-2'→ 'FG-R-2216LE26'
      'FG-R-2180LE25'          → 'FG-R-2180LE25'
    """
    if not isinstance(ref, str):
        ref = str(ref) if ref is not None else ""
    return ref.split(".")[0].split("-M")[0].strip() if ref else ""


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
    if columna_waybill not in df.columns and "Waybill Number" in df.columns:
        df[columna_waybill] = df["Waybill Number"]
        logger.info("   🔄 'Waybill Number' promovido a 'Reference' (alias)")
    
    if columna_peso not in df.columns:
        for alias in ["Gross Weight", "Gross Weight (Kgs)", "Peso Bruto (Kgs)"]:
            if alias in df.columns:
                df[columna_peso] = df[alias]
                logger.info(f"   🔄 '{alias}' promovido a '{columna_peso}' (alias)")
                break
    
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
    
    columnas_criticas = [columna_waybill, columna_peso, columna_item]
    faltantes = [c for c in columnas_criticas if c not in df.columns]
    if faltantes:
        raise ValueError(
            f"Columnas críticas faltantes en Outbound: {faltantes}. "
            f"Columnas disponibles: {list(df.columns)}"
        )
    
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
    
    # ═════════════════════════════════════════════════════════
    # 🔧 PASO 4: APLICAR COSTOS VARIABLES (v4 — fix bug $0.00)
    # ═════════════════════════════════════════════════════════
    logger.info("💰 Aplicando costos por Waybill...")
    
    # 🆕 DIAGNÓSTICO DE INPUT
    if df_costos is not None:
        logger.info(f"   🔍 INPUT: df_costos tiene {len(df_costos)} filas")
        logger.info(f"   🔍 INPUT: columnas={list(df_costos.columns)}")
        if "Fix Cost" in df_costos.columns:
            suma_entrada = float(
                pd.to_numeric(df_costos["Fix Cost"], errors="coerce").sum()
            )
            primeros_3 = df_costos[["Reference", "Fix Cost"]].head(3).to_dict("records")
            logger.info(f"   🔍 INPUT: Suma Fix Cost = ${suma_entrada:,.2f}")
            logger.info(f"   🔍 INPUT: Primeros 3 = {primeros_3}")
    
    # 🔑 NOMBRE INTERNO ÚNICO — evita colisión con 'Fix Cost' que el sistema
    # de mapeo renombró internamente a 'Costo_2'
    COL_COSTO_INTERNO = "__costo_aplicado__"
    
    # Inicializar con costo default
    df[COL_COSTO_INTERNO] = float(costo_fijo)
    
    if df_costos is not None and len(df_costos) > 0:
        # Preparar mapas de costos
        df_costos_temp = df_costos.copy()
        df_costos_temp["Reference"] = df_costos_temp["Reference"].astype(str).str.strip()
        df_costos_temp["Fix Cost"] = pd.to_numeric(
            df_costos_temp["Fix Cost"], errors="coerce"
        )
        df_costos_temp = df_costos_temp.dropna(subset=["Fix Cost"])
        df_costos_temp = df_costos_temp[df_costos_temp["Fix Cost"] > 0]
        df_costos_temp["Reference_Base"] = df_costos_temp["Reference"].apply(
            _extraer_reference_base
        )
        
        # Mapa 1: match exacto + Mapa 2: match por base
        mapa_exacto = dict(zip(
            df_costos_temp["Reference"],
            df_costos_temp["Fix Cost"],
        ))
        mapa_base = dict(zip(
            df_costos_temp["Reference_Base"],
            df_costos_temp["Fix Cost"],
        ))
        
        logger.info(
            f"   📋 Tabla preparada: {len(mapa_exacto)} exact + {len(mapa_base)} base"
        )
        
        # Función de búsqueda con fallback en cascada
        def _buscar_costo(waybill_ref) -> float:
            if not isinstance(waybill_ref, str):
                waybill_ref = str(waybill_ref) if waybill_ref is not None else ""
            if not waybill_ref or waybill_ref.lower() == "nan":
                return float(costo_fijo)
            
            # Intento 1: Match exacto
            if waybill_ref in mapa_exacto:
                return float(mapa_exacto[waybill_ref])
            
            # Intento 2: Match por reference base
            base = _extraer_reference_base(waybill_ref)
            if base in mapa_base:
                return float(mapa_base[base])
            
            # Intento 3: Buscar si alguna clave del mapa está contenida en el waybill
            for ref_key, costo_val in mapa_base.items():
                if ref_key and ref_key in waybill_ref:
                    return float(costo_val)
            
            # Fallback al default
            return float(costo_fijo)
        
        # Aplicar a la columna interna (nombre único)
        df[COL_COSTO_INTERNO] = df[columna_waybill].apply(_buscar_costo).astype(float)
        
        # ── VERIFICACIÓN POST-aplicación ──
        n_variables = int((df[COL_COSTO_INTERNO] != costo_fijo).sum())
        n_default = int((df[COL_COSTO_INTERNO] == costo_fijo).sum())
        suma_aplicada = float(
            df.groupby(columna_waybill)[COL_COSTO_INTERNO].first().sum()
        )
        
        logger.info(f"   ✅ {n_variables} filas con costo variable aplicado")
        logger.info(f"   ℹ️ {n_default} filas con costo default ${costo_fijo}")
        logger.info(f"   💰 Suma de costos únicos por Waybill: ${suma_aplicada:,.2f}")
        
        # Si la suma es 0, mostrar muestra para debugging
        if suma_aplicada == 0:
            muestra_valores = (
                df[[columna_waybill, COL_COSTO_INTERNO]]
                .head(5)
                .to_dict("records")
            )
            logger.error(
                f"   🚨 SUMA = $0 — Primeros 5 valores aplicados: {muestra_valores}"
            )
    else:
        logger.info(f"   ℹ️ Sin tabla de costos variables. Usando default: ${costo_fijo}")
    
    # 🔑 FINAL: Borrar columna 'Fix Cost' que pudo venir del mapeador
    # y crearla DESDE __costo_aplicado__ con los valores correctos
    if "Fix Cost" in df.columns:
        df = df.drop(columns=["Fix Cost"])
    df["Fix Cost"] = df[COL_COSTO_INTERNO].astype(float)
    df = df.drop(columns=[COL_COSTO_INTERNO])
    
    suma_fix_cost_total = float(df["Fix Cost"].sum())
    logger.info(
        f"   ✅ Columna 'Fix Cost' creada con suma total = ${suma_fix_cost_total:,.2f}"
    )
    
    # ─────────────────────────────────────────────────────────
    # PASO 5: CALCULAR %PROPORCIÓN Y CALC_EXP
    # ─────────────────────────────────────────────────────────
    logger.info("🧮 Calculando %Proporción y Calc_Exp...")
    
    df["Peso Total Waybill"] = df.groupby(columna_waybill)[columna_peso].transform("sum")
    df["%Proporcion"] = df[columna_peso] / df["Peso Total Waybill"]
    df["%Proporcion"] = df["%Proporcion"].fillna(0)
    df["Calc_Exp"] = df["%Proporcion"] * df["Fix Cost"]
    
    # Alias para retrocompatibilidad
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
    # PASO 8: MÉTRICAS
    # ─────────────────────────────────────────────────────────
    num_waybills = df[columna_waybill].nunique()
    
    # Costo esperado = suma de Fix Cost únicos por Waybill
    costo_esperado = float(
        df.groupby(columna_waybill)["Fix Cost"]
        .first()
        .sum()
    )
    
    costo_calculado = float(df["Calc_Exp"].sum())
    diferencia = abs(costo_esperado - costo_calculado)
    
    # Detectar modo de costo
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
        
        # ──── Modo costo ────
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
