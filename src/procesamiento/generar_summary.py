"""
Generador del SUMMARY consolidado.

REGLAS DE NEGOCIO (de la hoja REGLAS_PROCESO, sección 'PROCESO SUMMARY'):
═══════════════════════════════════════════════════════════════════════════
1. Combina resultados de las 3 operaciones: Outbound + Sea + Land
2. Estructura del Summary:
   - Sección %PCT:      Sea, Land, Outbound por cada BU
   - Sección Arg. Var $: Montos totales por BU
3. 🔴 REGLA ESPECIAL SEA:
   - Para cálculo de %PCT, EXCLUIR: 'Capex', 'MCS'
   - Solo contar BUs estándar: M01, M19, M23, M45, M46 (o los activos del mes)
   - Los MONTOS absolutos sí se reportan completos
4. 🟢 BUs DINÁMICOS:
   - NO asumir que serán los mismos del mes anterior
   - Detectar TODOS los BU presentes en los datos actuales
   - Unificar BUs de las 3 hojas (puede que un BU exista en Sea pero no en Land)
═══════════════════════════════════════════════════════════════════════════
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field

from src.utils.logger import configurar_logger

logger = configurar_logger("generar_summary")


# ============================================================
# CONSTANTES DE EXCLUSIÓN
# ============================================================
# BUs que se EXCLUYEN del cálculo de %PCT en Sea (pero NO de los montos)
BUS_EXCLUIDOS_SEA_PCT = {"Capex", "MCS"}

# Orden preferido de BUs en la presentación final (los desconocidos van al final)
ORDEN_BUS_ESTANDAR = ["M01", "M19", "M23", "M45", "M46"]


# ============================================================
# ESTRUCTURA DE RESULTADO
# ============================================================
@dataclass
class ResultadoSummary:
    """Contenedor de resultados del Summary consolidado."""
    tabla_pct: pd.DataFrame          # Tabla de %PCT por BU (3 filas: Sea/Land/Outbound)
    tabla_montos: pd.DataFrame       # Tabla de montos $ por BU
    tabla_consolidada: pd.DataFrame  # Vista combinada larga (para análisis)
    metricas: Dict[str, any] = field(default_factory=dict)
    advertencias: List[str] = field(default_factory=list)
    bus_orden: List[str] = field(default_factory=list)  # Orden final de BUs


# ============================================================
# FUNCIONES AUXILIARES
# ============================================================
def _detectar_bus_unificados(
    resumen_sea: pd.DataFrame,
    resumen_land: pd.DataFrame,
    resumen_outbound: pd.DataFrame,
    incluir_excluidos: bool = True,
) -> List[str]:
    """
    Unifica los BUs presentes en los 3 procesadores.
    Respeta el orden estándar (M01, M19, M23, M45, M46) y agrega
    BUs nuevos/especiales al final.
    
    Args:
        incluir_excluidos: Si True, incluye Capex/MCS al final (para tabla de montos)
                          Si False, los omite (para tabla de %PCT)
    """
    bus_sea = set(resumen_sea["BU"].dropna().unique()) if "BU" in resumen_sea.columns else set()
    bus_land = set(resumen_land["BU"].dropna().unique()) if "BU" in resumen_land.columns else set()
    bus_outbound = set(resumen_outbound["BU"].dropna().unique()) if "BU" in resumen_outbound.columns else set()
    
    todos = bus_sea | bus_land | bus_outbound
    
    # Ordenar: primero los estándar (en orden), luego el resto alfabético
    estandar_presentes = [bu for bu in ORDEN_BUS_ESTANDAR if bu in todos]
    no_estandar = sorted(todos - set(ORDEN_BUS_ESTANDAR))
    
    if not incluir_excluidos:
        no_estandar = [bu for bu in no_estandar if bu not in BUS_EXCLUIDOS_SEA_PCT]
    
    orden_final = estandar_presentes + no_estandar
    return orden_final


def _obtener_monto_por_bu(df_resumen: pd.DataFrame, bu: str, columna_monto: str) -> float:
    """Extrae el monto de un BU específico de un DataFrame de resumen."""
    if df_resumen is None or len(df_resumen) == 0 or "BU" not in df_resumen.columns:
        return 0.0
    
    fila = df_resumen[df_resumen["BU"] == bu]
    if len(fila) == 0:
        return 0.0
    
    return float(fila[columna_monto].iloc[0]) if columna_monto in fila.columns else 0.0


# ============================================================
# FUNCIÓN PRINCIPAL
# ============================================================
def generar_summary(
    resultado_outbound,
    resultado_sea,
    resultado_land,
) -> ResultadoSummary:
    """
    Genera el SUMMARY consolidado combinando los 3 procesadores.
    
    Args:
        resultado_outbound: Objeto ResultadoOutbound (del Bloque 3)
        resultado_sea: Objeto ResultadoSea (del Bloque 4)
        resultado_land: Objeto ResultadoLand (del Bloque 5)
    
    Returns:
        ResultadoSummary con:
        - tabla_pct: %PCT por BU (estructura: Type | M01 | M19 | ... )
        - tabla_montos: Montos $ por BU (estructura: Arg. Var $ | Total | M01 | ...)
        - tabla_consolidada: vista larga para análisis
        - métricas y advertencias
    """
    logger.info("=" * 60)
    logger.info("📊 INICIANDO GENERACIÓN DE SUMMARY CONSOLIDADO")
    logger.info("=" * 60)
    
    # ─────────────────────────────────────────────────────────
    # 1. VALIDACIONES INICIALES
    # ─────────────────────────────────────────────────────────
    advertencias = []
    
    if resultado_outbound is None:
        raise ValueError("Falta el resultado de OUTBOUND. Procésalo antes de generar Summary.")
    if resultado_sea is None:
        raise ValueError("Falta el resultado de SEA. Procésalo antes de generar Summary.")
    if resultado_land is None:
        raise ValueError("Falta el resultado de LAND. Procésalo antes de generar Summary.")
    
    df_sea = resultado_sea.resumen_bu.copy()
    df_land = resultado_land.resumen_bu.copy()
    df_out = resultado_outbound.resumen_bu.copy()
    
    logger.info(f"   BUs en Sea:      {df_sea['BU'].tolist() if 'BU' in df_sea.columns else []}")
    logger.info(f"   BUs en Land:     {df_land['BU'].tolist() if 'BU' in df_land.columns else []}")
    logger.info(f"   BUs en Outbound: {df_out['BU'].tolist() if 'BU' in df_out.columns else []}")
    
    # ─────────────────────────────────────────────────────────
    # 2. DETECTAR BUs UNIFICADOS (DINÁMICO - regla crítica)
    # ─────────────────────────────────────────────────────────
    bus_para_pct = _detectar_bus_unificados(df_sea, df_land, df_out, incluir_excluidos=False)
    bus_para_montos = _detectar_bus_unificados(df_sea, df_land, df_out, incluir_excluidos=True)
    
    logger.info(f"🎯 BUs para %PCT (sin Capex/MCS): {bus_para_pct}")
    logger.info(f"💰 BUs para montos $ (todos):      {bus_para_montos}")
    
    if not bus_para_pct:
        raise ValueError("No se detectaron BUs estándar para generar el Summary.")
    
    # ─────────────────────────────────────────────────────────
    # 3. CONSTRUIR TABLA DE %PCT (sección superior: filas 3-6 del Summary)
    # ─────────────────────────────────────────────────────────
    logger.info("🧮 Calculando tabla de %PCT...")
    
    # ── Sea %PCT: usar columna especial '%PCT (Summary)' que YA excluye Capex/MCS
    sea_pct_dict = {}
    if "%PCT (Summary)" in df_sea.columns:
        # Bloque 4 ya calculó este %PCT correctamente excluyendo Capex/MCS
        for bu in bus_para_pct:
            sea_pct_dict[bu] = _obtener_monto_por_bu(df_sea, bu, "%PCT (Summary)")
    else:
        # Fallback: calcular aquí
        df_sea_filtrado = df_sea[~df_sea["BU"].isin(BUS_EXCLUIDOS_SEA_PCT)]
        total_sea_filtrado = df_sea_filtrado["Amount (USD)"].sum() if "Amount (USD)" in df_sea_filtrado.columns else 0
        for bu in bus_para_pct:
            monto = _obtener_monto_por_bu(df_sea_filtrado, bu, "Amount (USD)")
            sea_pct_dict[bu] = monto / total_sea_filtrado if total_sea_filtrado > 0 else 0
    
    # ── Land %PCT: incluye TODOS los BUs (no hay exclusión en Land)
    land_pct_dict = {}
    total_land = df_land["Monto Total (USD)"].sum() if "Monto Total (USD)" in df_land.columns else 0
    for bu in bus_para_pct:
        monto = _obtener_monto_por_bu(df_land, bu, "Monto Total (USD)")
        land_pct_dict[bu] = monto / total_land if total_land > 0 else 0
    
    # ── Outbound %PCT: incluye todos
    out_pct_dict = {}
    total_out = df_out["Log. Exp (USD)"].sum() if "Log. Exp (USD)" in df_out.columns else 0
    for bu in bus_para_pct:
        monto = _obtener_monto_por_bu(df_out, bu, "Log. Exp (USD)")
        out_pct_dict[bu] = monto / total_out if total_out > 0 else 0
    
    # Construir DataFrame de %PCT (formato matching Summary!C3:H6)
    tabla_pct = pd.DataFrame([
        {"Type": "Sea %PCT",      **{bu: sea_pct_dict[bu]  for bu in bus_para_pct}},
        {"Type": "Land %PCT",     **{bu: land_pct_dict[bu] for bu in bus_para_pct}},
        {"Type": "Outbound %PCT", **{bu: out_pct_dict[bu]  for bu in bus_para_pct}},
    ])
    
    # ─────────────────────────────────────────────────────────
    # 4. CONSTRUIR TABLA DE MONTOS $ (sección inferior: filas 9-12)
    # ─────────────────────────────────────────────────────────
    logger.info("💰 Calculando tabla de montos $...")
    
    # ── Sea: montos totales (incluye Capex y MCS porque son costos reales)
    sea_montos = {}
    for bu in bus_para_montos:
        sea_montos[bu] = _obtener_monto_por_bu(df_sea, bu, "Amount (USD)")
    total_sea = sum(sea_montos.values())
    
    # ── Land: montos totales
    land_montos = {}
    for bu in bus_para_montos:
        land_montos[bu] = _obtener_monto_por_bu(df_land, bu, "Monto Total (USD)")
    total_land_full = sum(land_montos.values())
    
    # ── Outbound: montos totales
    out_montos = {}
    for bu in bus_para_montos:
        out_montos[bu] = _obtener_monto_por_bu(df_out, bu, "Log. Exp (USD)")
    total_out_full = sum(out_montos.values())
    
    # Construir DataFrame de montos (formato matching Summary!B9:H12)
    tabla_montos = pd.DataFrame([
        {"Arg. Var $": "Sea",      "Total": total_sea,      **sea_montos},
        {"Arg. Var $": "Land",     "Total": total_land_full, **land_montos},
        {"Arg. Var $": "Outbound", "Total": total_out_full,  **out_montos},
    ])
    
    # ─────────────────────────────────────────────────────────
    # 5. CONSTRUIR TABLA CONSOLIDADA (formato largo, útil para análisis)
    # ─────────────────────────────────────────────────────────
    filas_consolidadas = []
    for bu in bus_para_montos:
        filas_consolidadas.append({
            "BU": bu,
            "Sea Monto (USD)":      sea_montos.get(bu, 0),
            "Sea %PCT":             sea_pct_dict.get(bu, 0),
            "Land Monto (USD)":     land_montos.get(bu, 0),
            "Land %PCT":            land_pct_dict.get(bu, 0),
            "Outbound Monto (USD)": out_montos.get(bu, 0),
            "Outbound %PCT":        out_pct_dict.get(bu, 0),
            "TOTAL (USD)":          sea_montos.get(bu, 0) + land_montos.get(bu, 0) + out_montos.get(bu, 0),
            "Excluido de %PCT Sea": bu in BUS_EXCLUIDOS_SEA_PCT,
        })
    tabla_consolidada = pd.DataFrame(filas_consolidadas)
    
    # Agregar fila TOTAL al final
    fila_total = {
        "BU": "TOTAL",
        "Sea Monto (USD)":      total_sea,
        "Sea %PCT":             sum(sea_pct_dict.values()),
        "Land Monto (USD)":     total_land_full,
        "Land %PCT":            sum(land_pct_dict.values()),
        "Outbound Monto (USD)": total_out_full,
        "Outbound %PCT":        sum(out_pct_dict.values()),
        "TOTAL (USD)":          total_sea + total_land_full + total_out_full,
        "Excluido de %PCT Sea": False,
    }
    tabla_consolidada = pd.concat(
        [tabla_consolidada, pd.DataFrame([fila_total])], 
        ignore_index=True
    )
    
    # ─────────────────────────────────────────────────────────
    # 6. VALIDACIONES POST-CÁLCULO
    # ─────────────────────────────────────────────────────────
    # Validar que la suma de %PCT por fila sea ≈ 100% (con tolerancia)
    suma_pct_sea = sum(sea_pct_dict.values())
    suma_pct_land = sum(land_pct_dict.values())
    suma_pct_out = sum(out_pct_dict.values())
    
    tolerancia = 0.0001  # 0.01%
    
    if abs(suma_pct_sea - 1.0) > tolerancia and suma_pct_sea > 0:
        msg = f"Suma de %PCT Sea = {suma_pct_sea:.4%} (debería ser 100%)"
        advertencias.append(msg)
        logger.warning(f"⚠️ {msg}")
    
    if abs(suma_pct_land - 1.0) > tolerancia and suma_pct_land > 0:
        msg = f"Suma de %PCT Land = {suma_pct_land:.4%} (debería ser 100%)"
        advertencias.append(msg)
        logger.warning(f"⚠️ {msg}")
    
    if abs(suma_pct_out - 1.0) > tolerancia and suma_pct_out > 0:
        msg = f"Suma de %PCT Outbound = {suma_pct_out:.4%} (debería ser 100%)"
        advertencias.append(msg)
        logger.warning(f"⚠️ {msg}")
    
    # Detectar BUs nuevos (no estándar) que aparecieron este mes
    bus_nuevos = [bu for bu in bus_para_montos if bu not in ORDEN_BUS_ESTANDAR]
    if bus_nuevos:
        msg = (
            f"BUs no estándar detectados: {bus_nuevos}. "
            f"Revisa si son correctos (regla: los BUs pueden cambiar mes a mes)."
        )
        advertencias.append(msg)
        logger.info(f"ℹ️ {msg}")
    
    # ─────────────────────────────────────────────────────────
    # 7. MÉTRICAS GENERALES
    # ─────────────────────────────────────────────────────────
    metricas = {
        "total_bus_pct": len(bus_para_pct),
        "total_bus_montos": len(bus_para_montos),
        "bus_pct": bus_para_pct,
        "bus_montos": bus_para_montos,
        "bus_excluidos_pct": list(BUS_EXCLUIDOS_SEA_PCT & set(bus_para_montos)),
        "bus_nuevos": bus_nuevos,
        "total_sea_usd": round(total_sea, 2),
        "total_land_usd": round(total_land_full, 2),
        "total_outbound_usd": round(total_out_full, 2),
        "gran_total_usd": round(total_sea + total_land_full + total_out_full, 2),
        "suma_pct_sea": round(suma_pct_sea, 6),
        "suma_pct_land": round(suma_pct_land, 6),
        "suma_pct_outbound": round(suma_pct_out, 6),
    }
    
    # ─────────────────────────────────────────────────────────
    # 8. LOG FINAL
    # ─────────────────────────────────────────────────────────
    logger.info("─" * 60)
    logger.info(f"💰 Sea total:       ${metricas['total_sea_usd']:>12,.2f}")
    logger.info(f"💰 Land total:      ${metricas['total_land_usd']:>12,.2f}")
    logger.info(f"💰 Outbound total:  ${metricas['total_outbound_usd']:>12,.2f}")
    logger.info(f"💰 GRAN TOTAL:      ${metricas['gran_total_usd']:>12,.2f}")
    logger.info(f"✅ Sea %PCT suma:        {metricas['suma_pct_sea']:.2%}")
    logger.info(f"✅ Land %PCT suma:       {metricas['suma_pct_land']:.2%}")
    logger.info(f"✅ Outbound %PCT suma:   {metricas['suma_pct_outbound']:.2%}")
    
    if metricas["bus_excluidos_pct"]:
        logger.info(f"🚫 BUs excluidos de %PCT Sea: {metricas['bus_excluidos_pct']}")
    
    logger.info("=" * 60)
    
    return ResultadoSummary(
        tabla_pct=tabla_pct,
        tabla_montos=tabla_montos,
        tabla_consolidada=tabla_consolidada,
        metricas=metricas,
        advertencias=advertencias,
        bus_orden=bus_para_montos,
    )


# ============================================================
# FÓRMULAS EXCEL EQUIVALENTES (para Bloque 9 - exportación)
# ============================================================
def obtener_formulas_excel() -> Dict[str, str]:
    """
    Retorna las fórmulas Excel del Summary que se inyectarán en el archivo de salida.
    Estas son las mismas fórmulas que aparecen en tu hoja REGLAS_PROCESO (líneas 87-89),
    pero ajustadas para usar la nueva estructura del software.
    """
    return {
        "sea_pct_excluyendo_capex_mcs": (
            '=IFERROR(XLOOKUP([@BU], Sea_Resumen[BU], Sea_Resumen[%PCT (Summary)], 0), 0)'
        ),
        "land_pct": (
            '=IFERROR(XLOOKUP([@BU], Land_Resumen[BU], Land_Resumen[%PCT], 0), 0)'
        ),
        "outbound_pct": (
            '=IFERROR(XLOOKUP([@BU], Outbound_Resumen[BU], Outbound_Resumen[%PCT], 0), 0)'
        ),
        "sea_monto": (
            '=IFERROR(XLOOKUP([@BU], Sea_Resumen[BU], Sea_Resumen[Amount (USD)], 0), 0)'
        ),
        "land_monto": (
            '=IFERROR(XLOOKUP([@BU], Land_Resumen[BU], Land_Resumen[Monto Total (USD)], 0), 0)'
        ),
        "outbound_monto": (
            '=IFERROR(XLOOKUP([@BU], Outbound_Resumen[BU], Outbound_Resumen[Log. Exp (USD)], 0), 0)'
        ),
        "total_por_operacion": (
            '=SUM([@[M01]:[M46]])'  # Suma horizontal de todos los BUs
        ),
        "gran_total": (
            '=SUM(Summary_Montos[Total])'
        ),
    }