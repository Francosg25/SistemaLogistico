"""
Procesador de Exportaciones (OUTBOUND).

REGLAS DE NEGOCIO:
═══════════════════════════════════════════════════════════════
1. Agrupación: Por 'Reference' (Waybill Number)
2. Costo Fijo: $1,500 USD por Reference (parametrizable)
3. Inferencia BU: Extraer del patrón del Reference
   - FG-R-2208LE26.M46/M45 → BU = M45 (segundo)
   - FG-R-2202LE26.M19 → BU = M19 (único)
4. Cálculo:
   - %Proportion = Peso_Item / Peso_Total_Reference
   - Calc_Exp = %Proportion × Costo_Fijo_Reference
5. Resultado: Agrupar por BU (suma de Calc_Exp)
═══════════════════════════════════════════════════════════════
"""
import pandas as pd
import numpy as np
from typing import Dict, Optional
from dataclasses import dataclass, field

from src.reglas.inferencia_bu import (
    inferir_bu_desde_reference,
    obtener_todos_los_bus,
)
from src.utils.logger import configurar_logger

logger = configurar_logger("procesar_outbound")


# ============================================================
# ESTRUCTURA DE RESULTADO
# ============================================================
@dataclass
class ResultadoOutbound:
    """Contenedor de resultados del procesamiento Outbound."""
    detalle: pd.DataFrame                 # Cada item con su costo asignado
    resumen_bu: pd.DataFrame              # Resumen agrupado por BU
    referencias: pd.DataFrame             # Tabla de References con BU y costo
    metricas: Dict[str, any] = field(default_factory=dict)  # Estadísticas generales
    advertencias: list = field(default_factory=list)        # Issues detectados


# ============================================================
# FUNCIÓN PRINCIPAL
# ============================================================
def procesar_outbound(
    df_outbound: pd.DataFrame,
    costo_fijo: float = 1500.0,
    columna_reference: str = "Reference",
    columna_peso: str = "Gross Weight",
    columna_waybill: str = "Waybill Number",
    columna_item: str = "Item",
    columna_qty: str = "Qty Pzas",
) -> ResultadoOutbound:
    """
    Procesa el reporte de exportaciones aplicando todas las reglas de negocio.
    
    Args:
        df_outbound: DataFrame ya cargado y normalizado (output del Bloque 2)
        costo_fijo: Costo fijo por Reference (default $1,500 USD)
        columna_reference: Nombre de la columna Reference
        columna_peso: Nombre de la columna de peso bruto
        columna_waybill: Nombre de la columna Waybill Number
        columna_item: Nombre de la columna Item
        columna_qty: Nombre de la columna de cantidad
    
    Returns:
        ResultadoOutbound con detalle, resumen_bu, referencias y métricas
    
    Raises:
        ValueError: Si faltan columnas o los datos son inválidos
    """
    logger.info("=" * 60)
    logger.info("📤 INICIANDO PROCESAMIENTO OUTBOUND")
    logger.info("=" * 60)
    
    # ─────────────────────────────────────────────────────────
    # 1. VALIDACIONES INICIALES
    # ─────────────────────────────────────────────────────────
    if df_outbound is None or len(df_outbound) == 0:
        raise ValueError("El DataFrame de Outbound está vacío.")
    
    columnas_requeridas = [columna_reference, columna_peso, columna_item]
    faltantes = [c for c in columnas_requeridas if c not in df_outbound.columns]
    if faltantes:
        raise ValueError(f"Faltan columnas obligatorias: {faltantes}")
    
    # Trabajamos sobre una copia para no modificar el original
    df = df_outbound.copy()
    advertencias = []
    
    logger.info(f"📊 Registros recibidos: {len(df)}")
    
    # ─────────────────────────────────────────────────────────
    # 2. LIMPIEZA: Eliminar filas sin Reference o sin peso
    # ─────────────────────────────────────────────────────────
    filas_antes = len(df)
    df = df.dropna(subset=[columna_reference])
    df = df[df[columna_reference].astype(str).str.strip() != ""]
    
    # Convertir peso a numérico (por si llega como string)
    df[columna_peso] = pd.to_numeric(df[columna_peso], errors="coerce")
    df = df.dropna(subset=[columna_peso])
    df = df[df[columna_peso] > 0]
    
    filas_descartadas = filas_antes - len(df)
    if filas_descartadas > 0:
        msg = f"Se descartaron {filas_descartadas} filas (sin Reference o peso inválido)"
        advertencias.append(msg)
        logger.warning(f"⚠️ {msg}")
    
    if len(df) == 0:
        raise ValueError("Todos los registros fueron descartados durante la limpieza.")
    
    # ─────────────────────────────────────────────────────────
    # 3. INFERENCIA DE BU DESDE EL REFERENCE
    # ─────────────────────────────────────────────────────────
    logger.info("🧠 Aplicando inferencia de BU desde Reference...")
    
    df["BU (Inferido)"] = df[columna_reference].apply(inferir_bu_desde_reference)
    df["Todos los BU"] = df[columna_reference].apply(
        lambda x: "/".join(obtener_todos_los_bus(x))
    )
    
    # Detectar references sin BU inferible
    sin_bu = df[df["BU (Inferido)"].isna()]
    if len(sin_bu) > 0:
        refs_sin_bu = sin_bu[columna_reference].unique().tolist()
        msg = f"{len(refs_sin_bu)} Reference(s) sin BU inferible: {refs_sin_bu[:5]}..."
        advertencias.append(msg)
        logger.warning(f"⚠️ {msg}")
    
    bus_unicos = df["BU (Inferido)"].dropna().unique().tolist()
    logger.info(f"   BUs detectados: {sorted(bus_unicos)}")
    
    # ─────────────────────────────────────────────────────────
    # 4. CÁLCULO DE %PROPORTION POR REFERENCE
    # ─────────────────────────────────────────────────────────
    logger.info("🧮 Calculando %Proportion y Calc_Exp...")
    
    # Peso total por Reference (equivalente a SUMIFS de Excel)
    df["Peso Total Reference"] = df.groupby(columna_reference)[columna_peso].transform("sum")
    
    # %Proportion = Peso_Item / Peso_Total_Reference
    df["%Proportion"] = df[columna_peso] / df["Peso Total Reference"]
    df["%Proportion"] = df["%Proportion"].fillna(0)
    
    # Costo fijo por Reference (puede variar si en el futuro se hace dinámico)
    df["Fix Cost"] = costo_fijo
    
    # Calc_Exp = %Proportion × Costo_Fijo
    df["Calc_Exp"] = df["%Proportion"] * df["Fix Cost"]
    
    # ─────────────────────────────────────────────────────────
    # 5. CONSTRUCCIÓN DEL DETALLE (resultado por item)
    # ─────────────────────────────────────────────────────────
    columnas_detalle = [
        col for col in [
            "Inbound/Outbound",
            "Method",
            columna_reference,
            "BU (Inferido)",
            "Todos los BU",
            columna_waybill,
            columna_item,
            columna_qty,
            columna_peso,
            "Peso Total Reference",
            "%Proportion",
            "Fix Cost",
            "Calc_Exp",
        ] if col in df.columns
    ]
    detalle = df[columnas_detalle].copy().reset_index(drop=True)
    
    # ─────────────────────────────────────────────────────────
    # 6. TABLA DE REFERENCIAS (1 fila por Reference)
    # ─────────────────────────────────────────────────────────
    referencias = (
        df.groupby(columna_reference)
        .agg(
            **{
                "BU Asignado": ("BU (Inferido)", lambda x: x.mode().iloc[0] if len(x.mode()) > 0 else None),
                "Todos los BU": ("Todos los BU", "first"),
                "# Items": (columna_item, "count"),
                "Peso Total (Kgs)": (columna_peso, "sum"),
                "Fix Cost": ("Fix Cost", "first"),
                "Total Calculado": ("Calc_Exp", "sum"),
            }
        )
        .reset_index()
    )
    
    # ─────────────────────────────────────────────────────────
    # 7. RESUMEN POR BU (agrupación final)
    # ─────────────────────────────────────────────────────────
    resumen_bu = (
        df.dropna(subset=["BU (Inferido)"])
        .groupby("BU (Inferido)")
        .agg(
            **{
                "Log. Exp (USD)": ("Calc_Exp", "sum"),
                "# References": (columna_reference, "nunique"),
                "# Items": (columna_item, "count"),
                "Peso Total (Kgs)": (columna_peso, "sum"),
            }
        )
        .reset_index()
        .rename(columns={"BU (Inferido)": "BU"})
    )
    
    # Calcular %PCT
    total_exp = resumen_bu["Log. Exp (USD)"].sum()
    if total_exp > 0:
        resumen_bu["%PCT"] = resumen_bu["Log. Exp (USD)"] / total_exp
    else:
        resumen_bu["%PCT"] = 0.0
    
    # Ordenar de mayor a menor monto
    resumen_bu = resumen_bu.sort_values("Log. Exp (USD)", ascending=False).reset_index(drop=True)
    
    # ─────────────────────────────────────────────────────────
    # 8. MÉTRICAS GENERALES
    # ─────────────────────────────────────────────────────────
    num_referencias = referencias[columna_reference].nunique()
    costo_total_esperado = num_referencias * costo_fijo
    costo_total_calculado = detalle["Calc_Exp"].sum()
    diferencia = abs(costo_total_esperado - costo_total_calculado)
    
    metricas = {
        "total_items": len(detalle),
        "total_references": num_referencias,
        "total_bus": len(bus_unicos),
        "bus_detectados": sorted(bus_unicos),
        "costo_fijo_por_reference": costo_fijo,
        "costo_total_esperado": costo_total_esperado,
        "costo_total_calculado": round(costo_total_calculado, 2),
        "diferencia_validacion": round(diferencia, 2),
        "validacion_ok": diferencia < 0.01,
        "filas_descartadas": filas_descartadas,
    }
    
    # ─────────────────────────────────────────────────────────
    # 9. LOG FINAL
    # ─────────────────────────────────────────────────────────
    logger.info("─" * 60)
    logger.info(f"✅ Items procesados:       {metricas['total_items']}")
    logger.info(f"✅ References únicos:      {metricas['total_references']}")
    logger.info(f"✅ BUs detectados:         {metricas['total_bus']} → {metricas['bus_detectados']}")
    logger.info(f"💰 Costo total esperado:   ${metricas['costo_total_esperado']:,.2f}")
    logger.info(f"💰 Costo total calculado:  ${metricas['costo_total_calculado']:,.2f}")
    logger.info(f"🔍 Diferencia:             ${metricas['diferencia_validacion']:,.4f}")
    
    if metricas["validacion_ok"]:
        logger.info("✅ VALIDACIÓN: Conservación de costo OK")
    else:
        logger.error("❌ VALIDACIÓN: Conservación de costo FALLÓ")
        advertencias.append(
            f"Diferencia de ${metricas['diferencia_validacion']:.2f} entre "
            f"costo esperado y calculado."
        )
    
    logger.info("=" * 60)
    
    return ResultadoOutbound(
        detalle=detalle,
        resumen_bu=resumen_bu,
        referencias=referencias,
        metricas=metricas,
        advertencias=advertencias,
    )


# ============================================================
# FUNCIÓN AUXILIAR: GENERAR FÓRMULAS EXCEL (para Bloque 9)
# ============================================================
def obtener_formulas_excel() -> Dict[str, str]:
    """
    Retorna las fórmulas Excel equivalentes a los cálculos hechos en Python.
    Estas fórmulas se usarán en el Bloque 9 (generación de Excel) para que
    el usuario pueda auditar los cálculos directamente en la hoja.
    """
    return {
        "peso_total_reference": (
            '=SUMIFS([Gross Weight], [Reference], [@Reference])'
        ),
        "pct_proportion": (
            '=[@[Gross Weight]] / SUMIFS([Gross Weight], [Reference], [@Reference])'
        ),
        "calc_exp": (
            '=XLOOKUP([@Reference], TablaReferencias[Reference], '
            'TablaReferencias[Fix Cost]) * [@[%Proportion]]'
        ),
        "log_exp_bu": (
            '=SUMIFS([Calc_Exp], [BU (Inferido)], [@BU])'
        ),
        "pct_bu": (
            '=[@[Log. Exp (USD)]] / SUM([Log. Exp (USD)])'
        ),
    }