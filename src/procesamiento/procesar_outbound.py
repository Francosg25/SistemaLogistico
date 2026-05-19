"""
═══════════════════════════════════════════════════════════════
PROCESADOR OUTBOUND v5 — Integrado con motor nuevo
═══════════════════════════════════════════════════════════════
✅ MANTIENE 100% compatibilidad con pestania_outbound.py
✅ USA mapeo_columnas canónico (no hardcode de alias)
✅ USA cascada de BU de 4 niveles (Item → Subinv → Regex → Misc)
✅ LEE configuración de config.yaml (costos, tolerancias, palabras)
✅ Fix bug $0.00 (columna __costo_aplicado__)
✅ Fix bug $500 (sin hardcodes en resumen)
═══════════════════════════════════════════════════════════════
"""
import pandas as pd
import re
from typing import Dict, Optional
from dataclasses import dataclass, field

from src.reglas.regla_miscelaneus import (
    aplicar_regla_miscelaneus,
    cargar_config_miscelaneus,
)
from src.utils.logger import configurar_logger
from src.utils.config_loader import get_config
from src.ingesta.mapeo_columnas import obtener_columnas_canonicas

logger = configurar_logger("procesar_outbound")


@dataclass
class ResultadoOutbound:
    """Contrato compatible con pestania_outbound.py (NO cambiar campos)."""
    detalle: pd.DataFrame
    resumen_bu: pd.DataFrame
    resumen_waybills: pd.DataFrame
    metricas: Dict = field(default_factory=dict)
    advertencias: list = field(default_factory=list)
    reporte_miscelaneus: Dict = field(default_factory=dict)


# ════════════════════════════════════════════════════════════
# FUNCIONES AUXILIARES
# ════════════════════════════════════════════════════════════
def _inferir_bu_desde_waybill(waybill: str, usar_ultimo: bool = True) -> str:
    """
    Extrae el BU del Waybill Number.
    
    Args:
        waybill: el string del Waybill (ej. 'FG-R-2209LE26.M46/M45')
        usar_ultimo: si True, devuelve el ÚLTIMO BU (regla OUTBOUND)
                     si False, devuelve el PRIMERO (regla SEA/LAND)
    """
    if not isinstance(waybill, str):
        return "SIN_BU"

    bus = re.findall(r"M\d{2}", waybill.upper())
    if len(bus) == 0:
        return "SIN_BU"
    return bus[-1] if usar_ultimo else bus[0]


def _extraer_reference_base(ref) -> str:
    """Quita sufijos: 'FG-R-2209LE26.M46/M45' → 'FG-R-2209LE26'."""
    if not isinstance(ref, str):
        ref = str(ref) if ref is not None else ""
    return ref.split(".")[0].split("-M")[0].strip() if ref else ""


def _normalizar_alias_columnas(
    df: pd.DataFrame,
    columna_waybill: str,
    columna_peso: str,
    columna_item: str,
) -> pd.DataFrame:
    df = df.copy()
    canonicas = obtener_columnas_canonicas(df)

    # 🔧 NUEVO: Si pidieron 'Waybill Number' pero no existe, buscar 'Waybill' canónica
    if columna_waybill not in df.columns:
        if "Waybill" in canonicas:
            df[columna_waybill] = df[canonicas["Waybill"]]
            logger.info(f"   🔄 '{canonicas['Waybill']}' promovido a '{columna_waybill}'")
        elif "Reference" in canonicas:
            # Fallback: usar Reference (caso archivos sin Waybill Number)
            df[columna_waybill] = df[canonicas["Reference"]]
            logger.info(f"   🔄 Fallback: '{canonicas['Reference']}' → '{columna_waybill}'")

    # ... resto igual
    requeridos = {
        "Gross_Weight": columna_peso,
        "Item":         columna_item,
    }

    for canonica, nombre_interno in requeridos.items():
        if nombre_interno in df.columns:
            continue
        if canonica in canonicas:
            col_real = canonicas[canonica]
            df[nombre_interno] = df[col_real]
            logger.info(f"   🔄 '{col_real}' promovido a '{nombre_interno}'")

    return df


# ════════════════════════════════════════════════════════════
# FUNCIÓN PRINCIPAL
# ════════════════════════════════════════════════════════════
def procesar_outbound(
    df_outbound: pd.DataFrame,
    costo_fijo: Optional[float] = None,
    df_costos: Optional[pd.DataFrame] = None,
    columna_waybill: str = "Waybill Number",
    columna_peso: str = "Peso Bruto",
    columna_item: str = "Item",
    columna_bu: str = "BU",
) -> ResultadoOutbound:
    """
    Procesa OUTBOUND con prorrateo + regla Miscelaneus.

    Args:
        df_outbound: DataFrame crudo del Outbound
        costo_fijo: si None, lee de config.yaml ('costos.outbound.valor')
        df_costos: tabla opcional con [Reference, Fix Cost] para overrides
        columna_waybill: nombre de la columna de Waybill (default 'Reference')
        columna_peso: nombre de columna de peso (default 'Peso Bruto')
        columna_item: nombre de columna de Item
        columna_bu: nombre de columna de BU (default 'BU')

    Returns:
        ResultadoOutbound (compatible con pestania_outbound.py)
    """
    logger.info("=" * 60)
    logger.info("🚢 INICIANDO PROCESAMIENTO OUTBOUND (v5)")
    logger.info("=" * 60)

    # ─────────────────────────────────────────────────────────
    # CONFIGURACIÓN (lee de config.yaml, sin hardcodes)
    # ─────────────────────────────────────────────────────────
    config = get_config()

    if costo_fijo is None:
        costo_fijo = float(config.get("costos.outbound.valor", 1500))
        logger.info(f"   💰 Costo fijo desde config.yaml: ${costo_fijo}")
    else:
        costo_fijo = float(costo_fijo)

    tolerancia = float(config.get("validaciones.tolerancia_costo", 0.01))
    decimales = int(config.get("validaciones.decimales_monto", 2))
    bus_especiales_config = set(
        config.get("bus_especiales.excluidos_pct_sea", [])
    ) | {"Miscelaneus", "Machine", "Sin Asignar"}

    # ─────────────────────────────────────────────────────────
    # VALIDACIÓN INICIAL
    # ─────────────────────────────────────────────────────────
    if df_outbound is None or len(df_outbound) == 0:
        raise ValueError("El DataFrame de Outbound está vacío.")

    df = df_outbound.copy()
    advertencias = []

    # ─────────────────────────────────────────────────────────
    # PASO 0: NORMALIZACIÓN DE COLUMNAS (sistema canónico)
    # ─────────────────────────────────────────────────────────
    df = _normalizar_alias_columnas(df, columna_waybill, columna_peso, columna_item)

    logger.info(f"📊 Registros recibidos: {len(df)}")
    logger.info(f"   Columnas (primeras 15): {list(df.columns)[:15]}")

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
    
    # 🔧 NO truncar sufijos como -2, -3, etc. — son waybills distintos
    # (Solo strip de espacios, sin tocar el contenido)
    df[columna_waybill] = df[columna_waybill].astype(str).str.strip()   

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
            "Todos los registros fueron descartados. "
            "Verifica las columnas Waybill, Peso Bruto e Item."
        )

    # ─────────────────────────────────────────────────────────
    # PASO 2: INFERIR BU (regla segundo BU)
    # ─────────────────────────────────────────────────────────
    if columna_bu not in df.columns:
        logger.info("   🧠 Columna 'BU' no existe → infiriendo desde Waybill")
        df[columna_bu] = df[columna_waybill].apply(
            lambda w: _inferir_bu_desde_waybill(w, usar_ultimo=True)
        )
    else:
        mask_nulos = (
            df[columna_bu].isna()
            | (df[columna_bu].astype(str).str.strip() == "")
        )
        if mask_nulos.any():
            n = mask_nulos.sum()
            logger.info(f"   🧠 Infiriendo BU para {n} filas con BU vacío")
            df.loc[mask_nulos, columna_bu] = df.loc[mask_nulos, columna_waybill].apply(
                lambda w: _inferir_bu_desde_waybill(w, usar_ultimo=True)
            )

    df[columna_bu] = df[columna_bu].fillna("Sin Asignar")
    df.loc[df[columna_bu].astype(str).str.strip() == "", columna_bu] = "Sin Asignar"

    bus_originales = sorted(df[columna_bu].dropna().unique().tolist())
    logger.info(f"   ✅ BUs detectados: {bus_originales}")

    # ─────────────────────────────────────────────────────────
    # PASO 3: APLICAR REGLA MISCELANEUS
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

    n_reasignados = reporte_miscelaneus.get("items_reasignados", 0)
    if n_reasignados > 0:
        logger.info(f"   ✅ {n_reasignados} items → '{reporte_miscelaneus['bu_destino']}'")
    else:
        logger.info("   ℹ️ Sin items reasignados a Miscelaneus")

    # ═════════════════════════════════════════════════════════
    # PASO 4: APLICAR COSTOS VARIABLES (fix bug $0.00 mantenido)
    # ═════════════════════════════════════════════════════════
    logger.info("💰 Aplicando costos por Waybill...")

    if df_costos is not None:
        logger.info(f"   🔍 INPUT df_costos: {len(df_costos)} filas")
        if "Fix Cost" in df_costos.columns:
            suma_entrada = float(
                pd.to_numeric(df_costos["Fix Cost"], errors="coerce").sum()
            )
            logger.info(f"   🔍 Suma Fix Cost entrante: ${suma_entrada:,.2f}")

    COL_COSTO_INTERNO = "__costo_aplicado__"
    df[COL_COSTO_INTERNO] = float(costo_fijo)

    n_variables = 0
    n_default = df[columna_waybill].nunique()

    if df_costos is not None and len(df_costos) > 0:
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

        mapa_exacto = dict(zip(df_costos_temp["Reference"], df_costos_temp["Fix Cost"]))
        mapa_base = dict(zip(df_costos_temp["Reference_Base"], df_costos_temp["Fix Cost"]))

        logger.info(
            f"   📋 Tabla preparada: {len(mapa_exacto)} exact + {len(mapa_base)} base"
        )

        def _buscar_costo(waybill_ref) -> float:
            if not isinstance(waybill_ref, str):
                waybill_ref = str(waybill_ref) if waybill_ref is not None else ""
            if not waybill_ref or waybill_ref.lower() == "nan":
                return float(costo_fijo)
            if waybill_ref in mapa_exacto:
                return float(mapa_exacto[waybill_ref])
            base = _extraer_reference_base(waybill_ref)
            if base in mapa_base:
                return float(mapa_base[base])
            for ref_key, costo_val in mapa_base.items():
                if ref_key and ref_key in waybill_ref:
                    return float(costo_val)
            return float(costo_fijo)

        df[COL_COSTO_INTERNO] = df[columna_waybill].apply(_buscar_costo).astype(float)

        # Métricas POR WAYBILL ÚNICO (no por fila)
        costos_por_waybill = df.groupby(columna_waybill)[COL_COSTO_INTERNO].first()
        n_variables = int((costos_por_waybill != costo_fijo).sum())
        n_default = int((costos_por_waybill == costo_fijo).sum())
        suma_aplicada = float(costos_por_waybill.sum())

        logger.info(f"   ✅ {n_variables} waybills con costo variable")
        logger.info(f"   ℹ️ {n_default} waybills con costo default ${costo_fijo}")
        logger.info(f"   💰 Suma costos únicos por Waybill: ${suma_aplicada:,.2f}")
    else:
        logger.info(f"   ℹ️ Sin tabla variable. Default: ${costo_fijo}")

    # Crear 'Fix Cost' definitivo desde la columna interna
    if "Fix Cost" in df.columns:
        df = df.drop(columns=["Fix Cost"])
    df["Fix Cost"] = df[COL_COSTO_INTERNO].astype(float)
    df = df.drop(columns=[COL_COSTO_INTERNO])

    # ─────────────────────────────────────────────────────────
    # PASO 5: CALCULAR %PROPORCIÓN Y CALC_EXP
    # ─────────────────────────────────────────────────────────
    logger.info("🧮 Calculando %Proporción y Calc_Exp...")
    df["Peso Total Waybill"] = df.groupby(columna_waybill)[columna_peso].transform("sum")
    
    # Protección contra división por cero (motor_prorrateo style)
    peso_seguro = df["Peso Total Waybill"].replace(0, pd.NA)
    df["%Proporcion"] = (df[columna_peso] / peso_seguro).fillna(0)
    df["Calc_Exp"] = (df["%Proporcion"] * df["Fix Cost"]).round(decimales)
    df["Amount"] = df["Calc_Exp"]  # alias legacy

    # ─────────────────────────────────────────────────────────
    # PASO 6: VALIDACIÓN POR GRUPO (tolerancia $0.01 desde config)
    # ─────────────────────────────────────────────────────────
    cuadre = df.groupby(columna_waybill).agg(
        suma_calc=("Calc_Exp", "sum"),
        fix_cost=("Fix Cost", "first"),
    )
    cuadre["diferencia"] = (cuadre["suma_calc"] - cuadre["fix_cost"]).abs()
    cuadre["cuadra"] = cuadre["diferencia"] <= tolerancia
    grupos_descuadrados = cuadre[~cuadre["cuadra"]]

    if len(grupos_descuadrados) > 0:
        msg = f"🔴 {len(grupos_descuadrados)} waybill(s) NO cuadran (tolerancia ${tolerancia})"
        advertencias.append(msg)
        logger.warning(msg)

    # Marca de validación por fila
    df["Validacion"] = df[columna_waybill].map(
        lambda g: "🟢 OK" if cuadre.loc[g, "cuadra"] else "🔴 DIFF"
    )

    # ─────────────────────────────────────────────────────────
    # PASO 7: RESUMEN POR BU FINAL
    # ─────────────────────────────────────────────────────────
    logger.info("📊 Generando resumen por BU Final...")
    resumen_bu = (
        df.groupby("BU Final")
        .agg(**{
            "Monto Total (USD)": ("Calc_Exp", "sum"),
            "# Waybills":        (columna_waybill, "nunique"),
            "# Items":           (columna_item, "count"),
            "Peso Total (Kgs)":  (columna_peso, "sum"),
        })
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
    # PASO 8: RESUMEN POR WAYBILL
    # ─────────────────────────────────────────────────────────
    resumen_waybills = (
        df.groupby(columna_waybill)
        .agg(**{
            "BU Asignado": (
                "BU Final",
                lambda x: x.mode().iloc[0] if len(x.mode()) > 0 else "Sin Asignar"
            ),
            "# Items":          (columna_item, "count"),
            "Peso Total (Kgs)": (columna_peso, "sum"),
            "Fix Cost":         ("Fix Cost", "first"),
            "Total Amount":     ("Calc_Exp", "sum"),
        })
        .reset_index()
        .rename(columns={columna_waybill: "Waybill Number"})
    )

    # ─────────────────────────────────────────────────────────
    # PASO 9: MÉTRICAS (compatibles con pestania_outbound.py)
    # ─────────────────────────────────────────────────────────
    num_waybills = df[columna_waybill].nunique()
    costo_esperado = float(df.groupby(columna_waybill)["Fix Cost"].first().sum())
    costo_calculado = float(df["Calc_Exp"].sum())
    diferencia = abs(costo_esperado - costo_calculado)

    modo_costo = "variable" if n_variables > 0 else "default"

    # Detectar BUs especiales/nuevos (lee de config, no hardcoded)
    bus_finales = set(resumen_bu["BU"].tolist())
    bus_especiales = sorted(bus_finales & bus_especiales_config)
    bus_nuevos = sorted(
        bu for bu in bus_finales
        if bu not in bus_especiales_config
        and not re.match(r"^M\d{2}$", str(bu))
        and bu != "SIN_BU"
    )

    metricas = {
        # ──── Básicas ────
        "total_items":            len(df),
        "total_waybills":         num_waybills,
        "total_bus":              len(resumen_bu),
        "bus_detectados":         resumen_bu["BU"].tolist(),
        "costo_fijo_default":     costo_fijo,
        "costo_total_esperado":   round(costo_esperado, decimales),
        "costo_total_calculado":  round(costo_calculado, decimales),
        "diferencia_validacion":  round(diferencia, 4),
        "validacion_ok":          diferencia <= tolerancia,
        "tolerancia_aplicada":    tolerancia,
        "grupos_descuadrados":    len(grupos_descuadrados),
        "filas_descartadas":      filas_descartadas,

        # ──── Modo costo ────
        "modo_costo":             modo_costo,
        "n_waybills_variables":   n_variables,
        "n_waybills_default":     num_waybills - n_variables,

        # ──── BUs especiales / nuevos ────
        "bus_especiales":         bus_especiales,
        "bus_nuevos":             bus_nuevos,

        # ──── Reporte Miscelaneus ────
        "miscelaneus": {
            "items_reasignados": reporte_miscelaneus.get("items_reasignados", 0),
            "monto_reasignado":  reporte_miscelaneus.get("monto_reasignado", 0.0),
            "bus_origen":        reporte_miscelaneus.get("bus_origen_reasignados", []),
        },
    }

    # ─────────────────────────────────────────────────────────
    # LOG FINAL
    # ─────────────────────────────────────────────────────────
    logger.info("─" * 60)
    logger.info(f"✅ Items procesados:       {metricas['total_items']}")
    logger.info(f"✅ Waybills únicos:        {metricas['total_waybills']}")
    logger.info(f"✅ BUs detectados:         {metricas['bus_detectados']}")
    logger.info(f"💰 Costo esperado:         ${metricas['costo_total_esperado']:,.2f}")
    logger.info(f"💰 Costo calculado:        ${metricas['costo_total_calculado']:,.2f}")
    logger.info(f"💵 Modo costo:             {metricas['modo_costo']}")
    logger.info(f"🎯 Tolerancia:             ${metricas['tolerancia_aplicada']}")
    logger.info(f"🔴 Grupos descuadrados:    {metricas['grupos_descuadrados']}")
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

