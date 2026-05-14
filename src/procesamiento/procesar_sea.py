"""
Procesador de Importaciones Marítimas (SEA).

REGLAS DE NEGOCIO:
═══════════════════════════════════════════════════════════════
1. Agrupación:     Por 'Container Number'
2. Costo Fijo:     $2,500 USD por contenedor (parametrizable)
3. Cálculo:
   - %Pond = Peso_Item / Peso_Total_Contenedor
   - Cost  = %Pond × Costo_Fijo
4. BU:             Se toma directamente de la columna BU del reporte
5. REGLA CAPEX:    Items con 'CAPEX' en Item Code se inyectan manualmente
                   y absorben el 100% del costo del contenedor
═══════════════════════════════════════════════════════════════
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from dataclasses import dataclass, field

from src.procesamiento.capex_handler import (
    construir_registros_capex,
    validar_contenedores_capex,
    es_item_capex,
)
from src.reglas.regla_miscelaneus import aplicar_regla_miscelaneus, cargar_config_miscelaneus
from src.utils.logger import configurar_logger

logger = configurar_logger("procesar_sea")


@dataclass
class ResultadoSea:
    """Contenedor de resultados del procesamiento SEA."""
    detalle: pd.DataFrame                 # Cada item con su costo asignado
    resumen_bu: pd.DataFrame              # Resumen agrupado por BU
    contenedores: pd.DataFrame            # Tabla de contenedores con costo fijo
    metricas: Dict[str, any] = field(default_factory=dict)
    advertencias: List[str] = field(default_factory=list)
    issues_capex: Dict[str, List[str]] = field(default_factory=dict)


# ============================================================
# FUNCIÓN PRINCIPAL
# ============================================================
def procesar_sea(
    df_sea: pd.DataFrame,
    contenedores_capex: Optional[List[Dict[str, str]]] = None,
    costo_fijo: float = 2500.0,
    columna_bu: str = "BU",
    columna_item_code: str = "Item Code",
    columna_container: str = "Container Number",
    columna_peso: str = "Total Gross Weight",
) -> ResultadoSea:
    """
    Procesa el reporte de importaciones marítimas aplicando todas las reglas.
    
    Args:
        df_sea: DataFrame ya cargado y normalizado (output del Bloque 2)
        contenedores_capex: Lista de contenedores CAPEX ingresados manualmente
            Formato: [{'Container Number': 'XXX', 'Item Code': 'CAPEX-08'}, ...]
        costo_fijo: Costo fijo por contenedor (default $2,500 USD)
        columna_bu: Nombre de la columna BU
        columna_item_code: Nombre de la columna Item Code
        columna_container: Nombre de la columna Container Number
        columna_peso: Nombre de la columna de peso bruto total
    
    Returns:
        ResultadoSea con detalle, resumen_bu, contenedores, métricas y advertencias
    
    Raises:
        ValueError: Si faltan columnas o los datos son inválidos
    """
    logger.info("=" * 60)
    logger.info("🚢 INICIANDO PROCESAMIENTO SEA")
    logger.info("=" * 60)
    
    # ─────────────────────────────────────────────────────────
    # 1. VALIDACIONES INICIALES
    # ─────────────────────────────────────────────────────────
    if df_sea is None or len(df_sea) == 0:
        raise ValueError("El DataFrame de SEA está vacío.")
    
    columnas_req = [columna_bu, columna_item_code, columna_container, columna_peso]
    faltantes = [c for c in columnas_req if c not in df_sea.columns]
    if faltantes:
        raise ValueError(f"Faltan columnas obligatorias en SEA: {faltantes}")
    
    df = df_sea.copy()
    advertencias = []
    contenedores_capex = contenedores_capex or []
    
    logger.info(f"📊 Registros del reporte: {len(df)}")
    logger.info(f"💰 Costo fijo por contenedor: ${costo_fijo:,.2f}")
    logger.info(f"🔴 Contenedores CAPEX manuales: {len(contenedores_capex)}")
    
    # ─────────────────────────────────────────────────────────
    # 2. LIMPIEZA: Eliminar filas sin contenedor o peso inválido
    # ─────────────────────────────────────────────────────────
    filas_antes = len(df)
    df = df.dropna(subset=[columna_container])
    df = df[df[columna_container].astype(str).str.strip() != ""]
    
    df[columna_peso] = pd.to_numeric(df[columna_peso], errors="coerce")
    df = df.dropna(subset=[columna_peso])
    df = df[df[columna_peso] > 0]
    
    filas_descartadas = filas_antes - len(df)
    if filas_descartadas > 0:
        msg = f"Se descartaron {filas_descartadas} filas (sin contenedor o peso inválido)"
        advertencias.append(msg)
        logger.warning(f"⚠️ {msg}")
    
    # ─────────────────────────────────────────────────────────
    # 3. DETECTAR Y FILTRAR CAPEX QUE PUDIERAN ESTAR EN EL REPORTE
    # ─────────────────────────────────────────────────────────
    # Por regla, CAPEX NO debería venir en el reporte, pero validamos por seguridad
    df["Es CAPEX (en reporte)"] = df[columna_item_code].apply(es_item_capex)
    capex_en_reporte = df[df["Es CAPEX (en reporte)"]]
    
    if len(capex_en_reporte) > 0:
        msg = (
            f"Se encontraron {len(capex_en_reporte)} items CAPEX en el reporte fuente. "
            f"Por regla NO deberían venir aquí - se procesarán igualmente pero revisa el origen."
        )
        advertencias.append(msg)
        logger.warning(f"⚠️ {msg}")
    
    # ─────────────────────────────────────────────────────────
    # 4. VALIDAR CONTENEDORES CAPEX MANUALES
    # ─────────────────────────────────────────────────────────
    contenedores_en_reporte = df[columna_container].unique().tolist()
    issues_capex = validar_contenedores_capex(contenedores_capex, contenedores_en_reporte)
    
    if issues_capex["duplicados"]:
        msg = f"Contenedores CAPEX duplicados: {issues_capex['duplicados']}"
        advertencias.append(msg)
        logger.warning(f"⚠️ {msg}")
    
    if issues_capex["conflicto_con_reporte"]:
        msg = (
            f"⚠️ CONFLICTO: Contenedores CAPEX que YA existen en el reporte: "
            f"{issues_capex['conflicto_con_reporte']}. "
            f"Esto puede generar doble conteo."
        )
        advertencias.append(msg)
        logger.warning(f"⚠️ {msg}")

    config_misc = cargar_config_miscelaneus()
    df, reporte_miscelaneus = aplicar_regla_miscelaneus(
        df,
        columna_item="Item Code",              # Columna de Item en Sea
        columna_bu_origen="BU",
        columna_bu_destino="BU Final",
        palabras_sin_filtro=config_misc["palabras_sin_filtro"],
        palabras_con_filtro_guion=config_misc["palabras_con_filtro_guion"],
        bu_miscelaneus=config_misc["bu_destino"],
    )
    
    # ─────────────────────────────────────────────────────────
    # 5. CALCULAR %POND Y COST PARA REGISTROS NORMALES
    # ─────────────────────────────────────────────────────────
    logger.info("🧮 Calculando %Pond y Cost...")
    
    # Peso total por Container (equivalente a SUMIFS en Excel)
    df["Peso Total Contenedor"] = df.groupby(columna_container)[columna_peso].transform("sum")
    
    # %Pond = Peso_Item / Peso_Total_Contenedor
    df["%Pond"] = df[columna_peso] / df["Peso Total Contenedor"]
    df["%Pond"] = df["%Pond"].fillna(0)
    
    # Cost = %Pond × $2,500
    df["Cost"] = df["%Pond"] * costo_fijo
    df["Es CAPEX"] = False  # Marca para diferenciar de los inyectados
    
    # ─────────────────────────────────────────────────────────
    # 6. CONSTRUIR E INYECTAR REGISTROS CAPEX
    # ─────────────────────────────────────────────────────────
    df_capex = construir_registros_capex(contenedores_capex, costo_fijo)
    
    if len(df_capex) > 0:
        # Asegurar que las columnas del DF principal coincidan
        for col in df_capex.columns:
            if col not in df.columns:
                df[col] = np.nan
        for col in df.columns:
            if col not in df_capex.columns:
                df_capex[col] = np.nan
        
        # Concatenar (los CAPEX van al final del detalle)
        df_capex["Peso Total Contenedor"] = 0.0  # No hay peso en contenedores CAPEX
        df = pd.concat([df, df_capex[df.columns]], ignore_index=True)
        logger.info(f"✅ {len(df_capex)} registros CAPEX inyectados al detalle")
    
    # ─────────────────────────────────────────────────────────
    # 7. CONSTRUIR DETALLE FINAL
    # ─────────────────────────────────────────────────────────
    columnas_detalle = [
        columna_bu,
        columna_item_code,
        columna_container,
        columna_peso,
        "Peso Total Contenedor",
        "%Pond",
        "Cost",
        "Es CAPEX",
    ]
    detalle = df[columnas_detalle].copy().reset_index(drop=True)
    
    # ─────────────────────────────────────────────────────────
    # 8. TABLA DE CONTENEDORES (1 fila por Container)
    # ─────────────────────────────────────────────────────────
    # Cada contenedor (incluyendo CAPEX) tiene su costo fijo de $2,500
    contenedores = (
        detalle.groupby(columna_container)
        .agg(
            **{
                "# Items": (columna_item_code, "count"),
                "Peso Total (Kgs)": (columna_peso, "sum"),
                "Es Contenedor CAPEX": ("Es CAPEX", "any"),
                "Costo Distribuido": ("Cost", "sum"),
            }
        )
        .reset_index()
    )
    contenedores["Costo Fijo (USD)"] = costo_fijo
    
    # ─────────────────────────────────────────────────────────
    # 9. RESUMEN POR BU
    # ─────────────────────────────────────────────────────────
    resumen_bu = (
        detalle.dropna(subset=[columna_bu])
        .groupby(columna_bu)
        .agg(
            **{
                "Amount (USD)": ("Cost", "sum"),
                "# Items": (columna_item_code, "count"),
                "# Contenedores": (columna_container, "nunique"),
                "Peso Total (Kgs)": (columna_peso, "sum"),
            }
        )
        .reset_index()
        .rename(columns={columna_bu: "BU"})
    )
    
    # %PCT total (incluyendo Capex y MCS)
    total_amount = resumen_bu["Amount (USD)"].sum()
    if total_amount > 0:
        resumen_bu["%PCT (Total)"] = resumen_bu["Amount (USD)"] / total_amount
    else:
        resumen_bu["%PCT (Total)"] = 0.0
    
    # %PCT EXCLUYENDO Capex y MCS (para el Summary del Bloque 6)
    # Esta es la regla crítica: "Para %PCT del Summary: Excluir Capex y MCS"
    bus_excluidos = ["Capex", "MCS"]
    mask_summary = ~resumen_bu["BU"].isin(bus_excluidos)
    total_summary = resumen_bu.loc[mask_summary, "Amount (USD)"].sum()
    
    if total_summary > 0:
        resumen_bu["%PCT (Summary)"] = np.where(
            mask_summary,
            resumen_bu["Amount (USD)"] / total_summary,
            0.0  # Capex y MCS = 0% en el summary
        )
    else:
        resumen_bu["%PCT (Summary)"] = 0.0
    
    resumen_bu = resumen_bu.sort_values("Amount (USD)", ascending=False).reset_index(drop=True)
    
    # ─────────────────────────────────────────────────────────
    # 10. MÉTRICAS Y VALIDACIONES
    # ─────────────────────────────────────────────────────────
    num_contenedores = detalle[columna_container].nunique()
    costo_total_esperado = num_contenedores * costo_fijo
    costo_total_calculado = detalle["Cost"].sum()
    diferencia = abs(costo_total_esperado - costo_total_calculado)
    
    bus_detectados = sorted(detalle[columna_bu].dropna().unique().tolist())
    
    metricas = {
        "total_items": len(detalle),
        "items_regulares": int((~detalle["Es CAPEX"]).sum()),
        "items_capex": int(detalle["Es CAPEX"].sum()),
        "total_contenedores": num_contenedores,
        "contenedores_capex": len(contenedores_capex),
        "total_bus": len(bus_detectados),
        "bus_detectados": bus_detectados,
        "costo_fijo_por_contenedor": costo_fijo,
        "costo_total_esperado": costo_total_esperado,
        "costo_total_calculado": round(costo_total_calculado, 2),
        "diferencia_validacion": round(diferencia, 2),
        "validacion_ok": diferencia < 0.01,
        "filas_descartadas": filas_descartadas,
    }
    
    # ─────────────────────────────────────────────────────────
    # 11. LOG FINAL
    # ─────────────────────────────────────────────────────────
    logger.info("─" * 60)
    logger.info(f"✅ Items procesados:       {metricas['total_items']} "
                f"(regulares: {metricas['items_regulares']}, CAPEX: {metricas['items_capex']})")
    logger.info(f"✅ Contenedores únicos:    {metricas['total_contenedores']}")
    logger.info(f"✅ BUs detectados:         {metricas['total_bus']} → {bus_detectados}")
    logger.info(f"💰 Costo total esperado:   ${metricas['costo_total_esperado']:,.2f}")
    logger.info(f"💰 Costo total calculado:  ${metricas['costo_total_calculado']:,.2f}")
    logger.info(f"🔍 Diferencia:             ${metricas['diferencia_validacion']:,.4f}")
    
    if metricas["validacion_ok"]:
        logger.info("✅ VALIDACIÓN: Conservación de costo OK")
    else:
        logger.error("❌ VALIDACIÓN: Conservación de costo FALLÓ")
        advertencias.append(
            f"Diferencia de ${metricas['diferencia_validacion']:.2f} "
            f"entre costo esperado y calculado."
        )
    
    logger.info("=" * 60)
    
    return ResultadoSea(
        detalle=detalle,
        resumen_bu=resumen_bu,
        contenedores=contenedores,
        metricas=metricas,
        advertencias=advertencias,
        issues_capex=issues_capex,
    )


# ============================================================
# FÓRMULAS EXCEL EQUIVALENTES (para Bloque 9 - exportación)
# ============================================================
def obtener_formulas_excel() -> Dict[str, str]:
    """
    Retorna las fórmulas Excel equivalentes a los cálculos hechos en Python.
    Se usarán en la generación del Excel de salida para que el usuario
    pueda auditar los cálculos en la hoja.
    """
    return {
        "peso_total_contenedor": (
            '=SUMIFS([Total Gross Weight], [Container Number], [@[Container Number]])'
        ),
        "pct_pond_normal": (
            '=IFERROR([@[Total Gross Weight]] / '
            'SUMIFS([Total Gross Weight], [Container Number], [@[Container Number]]), 1)'
        ),
        "pct_pond_capex": (
            '=1'  # 100% siempre para CAPEX
        ),
        "cost_normal": (
            '=[@[%Pond]] * 2500'
        ),
        "cost_capex": (
            '=2500'  # Costo fijo completo para CAPEX
        ),
        "amount_bu": (
            '=SUMIFS([Cost], [BU], [@BU])'
        ),
        "pct_summary_excluyendo_capex_mcs": (
            '=IF(OR([@BU]="Capex", [@BU]="MCS"), 0, '
            '[@[Amount (USD)]] / SUMIFS([Amount (USD)], [BU], "<>Capex", [BU], "<>MCS"))'
        ),
    }