"""
Validador principal: orquesta todas las reglas de validación.

Recibe los resultados de los Bloques 3, 4, 5, 6 y produce un
ReporteValidacion consolidado para mostrar en la UI.
"""
from typing import Optional, List
from src.validaciones.reporte_validacion import ReporteValidacion, Hallazgo, Severidad
from src.validaciones.reglas_validacion import (
    validar_conservacion_costo,
    validar_suma_porcentajes,
    validar_pesos_no_negativos,
    validar_duplicados,
    validar_bu_asignado,
    validar_capex_cruzado,
    validar_pct_summary,
    validar_exclusion_capex_mcs,
    validar_contenedores_sin_items,
    validar_bus_conocidos,
)
from src.reglas.catalogo_manager import obtener_catalogo
from src.utils.logger import configurar_logger

logger = configurar_logger("validador")


# ============================================================
# FUNCIÓN PRINCIPAL
# ============================================================
def validar_todo(
    resultado_outbound=None,
    resultado_sea=None,
    resultado_land=None,
    resultado_summary=None,
) -> ReporteValidacion:
    """
    Ejecuta TODAS las validaciones contra los resultados recibidos.
    
    Args:
        resultado_outbound: ResultadoOutbound del Bloque 3 (puede ser None)
        resultado_sea: ResultadoSea del Bloque 4 (puede ser None)
        resultado_land: ResultadoLand del Bloque 5 (puede ser None)
        resultado_summary: ResultadoSummary del Bloque 6 (puede ser None)
    
    Returns:
        ReporteValidacion con todos los hallazgos
    """
    logger.info("=" * 60)
    logger.info("🔍 INICIANDO VALIDACIONES AUTOMÁTICAS")
    logger.info("=" * 60)
    
    reporte = ReporteValidacion()
    catalogo = obtener_catalogo()
    bus_conocidos = catalogo.bus_conocidos
    
    # ─────────────────────────────────────────────────────────
    # VALIDACIONES DE OUTBOUND
    # ─────────────────────────────────────────────────────────
    if resultado_outbound is not None:
        logger.info("📤 Validando OUTBOUND...")
        
        for h in validar_conservacion_costo("outbound", resultado_outbound.metricas):
            reporte.agregar(h)
        
        for h in validar_suma_porcentajes(
            "outbound",
            resultado_outbound.detalle,
            columna_grupo="Reference",
            columna_pct="%Proportion",
        ):
            reporte.agregar(h)
        
        for h in validar_pesos_no_negativos(
            "outbound",
            resultado_outbound.detalle,
            columna_peso="Gross Weight",
        ):
            reporte.agregar(h)
        
        for h in validar_duplicados(
            "outbound",
            resultado_outbound.detalle,
            columnas_clave=["Reference", "Item"],
        ):
            reporte.agregar(h)
        
        for h in validar_bu_asignado(
            "outbound",
            resultado_outbound.detalle,
            columna_bu="BU (Inferido)",
        ):
            reporte.agregar(h)
        
        for h in validar_bus_conocidos(
            "outbound", resultado_outbound.metricas, bus_conocidos
        ):
            reporte.agregar(h)
    
    # ─────────────────────────────────────────────────────────
    # VALIDACIONES DE SEA
    # ─────────────────────────────────────────────────────────
    if resultado_sea is not None:
        logger.info("🚢 Validando SEA...")
        
        for h in validar_conservacion_costo("sea", resultado_sea.metricas):
            reporte.agregar(h)
        
        for h in validar_suma_porcentajes(
            "sea",
            resultado_sea.detalle,
            columna_grupo="Container Number",
            columna_pct="%Pond",
        ):
            reporte.agregar(h)
        
        for h in validar_pesos_no_negativos(
            "sea",
            resultado_sea.detalle,
            columna_peso="Total Gross Weight",
            columna_es_capex="Es CAPEX",
        ):
            reporte.agregar(h)
        
        for h in validar_duplicados(
            "sea",
            resultado_sea.detalle,
            columnas_clave=["Container Number", "Item Code"],
        ):
            reporte.agregar(h)
        
        for h in validar_bu_asignado(
            "sea", resultado_sea.detalle, columna_bu="BU"
        ):
            reporte.agregar(h)
        
        for h in validar_capex_cruzado(resultado_sea.issues_capex):
            reporte.agregar(h)
        
        for h in validar_contenedores_sin_items(resultado_sea.detalle):
            reporte.agregar(h)
        
        for h in validar_bus_conocidos(
            "sea", resultado_sea.metricas, bus_conocidos
        ):
            reporte.agregar(h)
    
    # ─────────────────────────────────────────────────────────
    # VALIDACIONES DE LAND
    # ─────────────────────────────────────────────────────────
    if resultado_land is not None:
        logger.info("🚚 Validando LAND...")
        
        for h in validar_conservacion_costo("land", resultado_land.metricas):
            reporte.agregar(h)
        
        for h in validar_suma_porcentajes(
            "land",
            resultado_land.detalle,
            columna_grupo="Reference",
            columna_pct="%Pond",
        ):
            reporte.agregar(h)
        
        for h in validar_pesos_no_negativos(
            "land",
            resultado_land.detalle,
            columna_peso="Peso Bruto (Kgs)",
        ):
            reporte.agregar(h)
        
        for h in validar_duplicados(
            "land",
            resultado_land.detalle,
            columnas_clave=["Reference", "No. Parte Prov."],
        ):
            reporte.agregar(h)
        
        for h in validar_bu_asignado(
            "land", resultado_land.detalle, columna_bu="BU"
        ):
            reporte.agregar(h)
        
        for h in validar_bus_conocidos(
            "land", resultado_land.metricas, bus_conocidos
        ):
            reporte.agregar(h)
    
    # ─────────────────────────────────────────────────────────
    # VALIDACIONES DE SUMMARY
    # ─────────────────────────────────────────────────────────
    if resultado_summary is not None:
        logger.info("📊 Validando SUMMARY...")
        
        for h in validar_pct_summary(resultado_summary.metricas):
            reporte.agregar(h)
        
        for h in validar_exclusion_capex_mcs(resultado_summary):
            reporte.agregar(h)
    
    # ─────────────────────────────────────────────────────────
    # LOG FINAL
    # ─────────────────────────────────────────────────────────
    resumen = reporte.resumen()
    logger.info("─" * 60)
    logger.info(f"📊 Total validaciones: {resumen['total_validaciones']}")
    logger.info(f"🟢 OK:        {resumen['ok']}")
    logger.info(f"🟡 Warnings:  {resumen['warnings']}")
    logger.info(f"🔴 Errores:   {resumen['errores']}")
    logger.info(f"🎯 Estado global: {resumen['emoji_global']} {resumen['estado_global']}")
    logger.info(f"💾 ¿Puede exportar?: {'✅ SÍ' if resumen['puede_exportar'] else '❌ NO'}")
    logger.info("=" * 60)
    
    return reporte


# ============================================================
# FUNCIÓN AUXILIAR: VALIDAR SOLO UNA OPERACIÓN
# ============================================================
def validar_operacion(operacion: str, resultado) -> ReporteValidacion:
    """
    Valida solo una operación específica.
    Útil para validar SEA antes de procesar LAND, por ejemplo.
    """
    kwargs = {f"resultado_{operacion}": resultado}
    return validar_todo(**kwargs)