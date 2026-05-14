"""
Procesador de Exportaciones (OUTBOUND) - con soporte para costos variables.
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

from src.reglas.regla_miscelaneus import (
    aplicar_regla_miscelaneus,
    cargar_config_miscelaneus,
)

logger = configurar_logger("procesar_outbound")


@dataclass
class ResultadoOutbound:
    detalle: pd.DataFrame
    resumen_bu: pd.DataFrame
    referencias: pd.DataFrame
    metricas: Dict[str, any] = field(default_factory=dict)
    advertencias: list = field(default_factory=list)


def _asignar_bu_hibrido(row, columna_bu_directo: str = "BU", 
                        columna_reference: str = "Reference"):
    """Lógica híbrida: BU directo si existe, sino inferir del Reference."""
    bu_directo = row.get(columna_bu_directo)
    if bu_directo and isinstance(bu_directo, str) and bu_directo.strip():
        return bu_directo.strip()
    return inferir_bu_desde_reference(row.get(columna_reference, ""))


def procesar_outbound(
    df_outbound: pd.DataFrame,
    costo_fijo: float = 1500.0,
    df_costos: Optional[pd.DataFrame] = None,  # 🆕 Tabla de costos variables
    columna_reference: str = "Reference",
    columna_peso: str = "Gross Weight",
    columna_waybill: str = "Waybill Number",
    columna_item: str = "Item",
    columna_qty: str = "Qty Pzas",
    columna_bu_directo: str = "BU",
    
) -> ResultadoOutbound:
    
    logger.info("🔄 Aplicando regla Miscelaneus a Outbound...")

    config_misc = cargar_config_miscelaneus()
    df, reporte_miscelaneus = aplicar_regla_miscelaneus(
        df,
    columna_item=columna_item,                # "Item"
    columna_bu_origen="BU (Asignado)",        # Usar el BU ya asignado
    columna_bu_destino="BU Final",
    palabras_sin_filtro=config_misc["palabras_sin_filtro"],
    palabras_con_filtro_guion=config_misc["palabras_con_filtro_guion"],
    bu_miscelaneus=config_misc["bu_destino"],
    )

    # Usar "BU Final" en lugar de "BU (Inferido)" para compatibilidad
    df["BU (Inferido)"] = df["BU Final"]

    # Agregar al reporte:
    metricas["miscelaneus"] = {
        "items_reasignados": reporte_miscelaneus["items_reasignados"],
        "monto_reasignado": reporte_miscelaneus["monto_reasignado"],
    }
    
    """
    Procesa el reporte de exportaciones.
    
    🆕 Si se proporciona df_costos, usa costos variables por Reference.
    Si no, usa el costo_fijo para todos.
    
    Args:
        df_outbound: DataFrame con los datos de outbound
        costo_fijo: Costo default si no hay tabla de costos
        df_costos: DataFrame opcional con [Reference, Fix Cost]
    """
    logger.info("=" * 60)
    logger.info("📤 INICIANDO PROCESAMIENTO OUTBOUND")
    
    if df_costos is not None and len(df_costos) > 0:
        logger.info("💰 Modo: COSTOS VARIABLES por Reference")
    else:
        logger.info(f"💰 Modo: COSTO FIJO ${costo_fijo:,.0f} para todas las references")
    
    logger.info("=" * 60)
    
    # ─────────────────────────────────────────────────────────
    # 1. VALIDACIONES INICIALES
    # ─────────────────────────────────────────────────────────
    if df_outbound is None or len(df_outbound) == 0:
        raise ValueError("El DataFrame de Outbound está vacío.")
    
    df = df_outbound.copy()
    advertencias = []
    logger.info(f"📊 Registros recibidos: {len(df)}")
    
    # ─────────────────────────────────────────────────────────
    # 2. LIMPIEZA
    # ─────────────────────────────────────────────────────────
    filas_antes = len(df)
    df = df.dropna(subset=[columna_reference])
    df = df[df[columna_reference].astype(str).str.strip() != ""]
    df[columna_peso] = pd.to_numeric(df[columna_peso], errors="coerce")
    df = df.dropna(subset=[columna_peso])
    df = df[df[columna_peso] > 0]
    
    filas_descartadas = filas_antes - len(df)
    if filas_descartadas > 0:
        advertencias.append(f"Se descartaron {filas_descartadas} filas")
        logger.warning(f"⚠️ Filas descartadas: {filas_descartadas}")
    
    if len(df) == 0:
        raise ValueError(
            "Todos los registros fueron descartados. "
            "Verifica encabezados y datos del archivo."
        )
    
    # ─────────────────────────────────────────────────────────
    # 3. ASIGNACIÓN HÍBRIDA DE BU
    # ─────────────────────────────────────────────────────────
    df["BU (Asignado)"] = df.apply(
        lambda row: _asignar_bu_hibrido(row, columna_bu_directo, columna_reference),
        axis=1
    )
    
    def _metodo(row):
        bu_dir = row.get(columna_bu_directo, "")
        if bu_dir and isinstance(bu_dir, str) and bu_dir.strip():
            return "Directo (columna BU)"
        elif row.get("BU (Asignado)"):
            return "Inferido (del Reference)"
        return "Sin asignar"
    
    df["Método BU"] = df.apply(_metodo, axis=1)
    metodos_count = df["Método BU"].value_counts().to_dict()
    
    df["Todos los BU"] = df[columna_reference].apply(
        lambda x: "/".join(obtener_todos_los_bus(x))
    )
    
    # Filtrar sin BU
    sin_bu = df[df["BU (Asignado)"].isna() | (df["BU (Asignado)"] == "")]
    if len(sin_bu) > 0:
        advertencias.append(f"{len(sin_bu)} filas sin BU asignado")
        df = df[~(df["BU (Asignado)"].isna() | (df["BU (Asignado)"] == ""))]
    
    if len(df) == 0:
        raise ValueError("No se pudo asignar BU a ningún registro.")
    
    bus_unicos = df["BU (Asignado)"].dropna().unique().tolist()
    logger.info(f"   ✅ BUs detectados: {sorted(bus_unicos)}")
    
    # ─────────────────────────────────────────────────────────
    # 4. 🆕 ASIGNAR COSTO POR REFERENCE (VARIABLE O FIJO)
    # ─────────────────────────────────────────────────────────
    logger.info("💰 Asignando costo por Reference...")
    
    if df_costos is not None and len(df_costos) > 0:
        # Modo VARIABLE: hacer merge con la tabla de costos
        df_costos_limpio = df_costos[["Reference", "Fix Cost"]].copy()
        df_costos_limpio = df_costos_limpio.drop_duplicates(subset=["Reference"])
        
        df = df.merge(
            df_costos_limpio,
            on="Reference",
            how="left",
            suffixes=("", "_costo")
        )
        
        # Si alguna Reference no aparece en la tabla, usar costo_fijo como fallback
        references_sin_costo = df[df["Fix Cost"].isna()][columna_reference].unique().tolist()
        if references_sin_costo:
            advertencias.append(
                f"{len(references_sin_costo)} References sin costo en tabla. "
                f"Usando ${costo_fijo:,.0f} como fallback: {references_sin_costo[:3]}..."
            )
            logger.warning(f"   ⚠️ {len(references_sin_costo)} refs sin costo asignado")
        
        df["Fix Cost"] = df["Fix Cost"].fillna(costo_fijo)
        
        # Estadísticas
        costos_unicos = df_costos_limpio["Fix Cost"].nunique()
        logger.info(f"   📊 Costos variables aplicados ({costos_unicos} valores únicos)")
        logger.info(f"   💵 Rango: ${df['Fix Cost'].min():,.0f} - ${df['Fix Cost'].max():,.0f}")
    else:
        # Modo FIJO
        df["Fix Cost"] = costo_fijo
        logger.info(f"   💵 Costo fijo: ${costo_fijo:,.0f}")
    
    # ─────────────────────────────────────────────────────────
    # 5. CÁLCULO DE %PROPORTION Y CALC_EXP
    # ─────────────────────────────────────────────────────────
    logger.info("🧮 Calculando %Proportion y Calc_Exp...")
    
    df["Peso Total Reference"] = df.groupby(columna_reference)[columna_peso].transform("sum")
    df["%Proportion"] = df[columna_peso] / df["Peso Total Reference"]
    df["%Proportion"] = df["%Proportion"].fillna(0)
    df["Calc_Exp"] = df["%Proportion"] * df["Fix Cost"]
    
    # ─────────────────────────────────────────────────────────
    # 6. DETALLE
    # ─────────────────────────────────────────────────────────
    df["BU (Inferido)"] = df["BU (Asignado)"]
    
    columnas_detalle = [
        col for col in [
            "Inbound/Outbound", "Method", columna_reference,
            "BU (Inferido)", "Método BU", "Todos los BU",
            columna_waybill, columna_item, columna_qty,
            columna_peso, "Peso Total Reference",
            "%Proportion", "Fix Cost", "Calc_Exp",
        ] if col in df.columns
    ]
    detalle = df[columnas_detalle].copy().reset_index(drop=True)
    
    # ─────────────────────────────────────────────────────────
    # 7. TABLA DE REFERENCIAS
    # ─────────────────────────────────────────────────────────
    referencias = (
        df.groupby(columna_reference)
        .agg(**{
            "BU Asignado": ("BU (Inferido)", lambda x: x.mode().iloc[0] if len(x.mode()) > 0 else None),
            "Todos los BU": ("Todos los BU", "first"),
            "# Items": (columna_item, "count"),
            "Peso Total (Kgs)": (columna_peso, "sum"),
            "Fix Cost": ("Fix Cost", "first"),
            "Total Calculado": ("Calc_Exp", "sum"),
        })
        .reset_index()
    )
    
    # ─────────────────────────────────────────────────────────
    # 8. RESUMEN POR BU
    # ─────────────────────────────────────────────────────────
    resumen_bu = (
        df.dropna(subset=["BU (Inferido)"])
        .groupby("BU (Inferido)")
        .agg(**{
            "Log. Exp (USD)": ("Calc_Exp", "sum"),
            "# References": (columna_reference, "nunique"),
            "# Items": (columna_item, "count"),
            "Peso Total (Kgs)": (columna_peso, "sum"),
        })
        .reset_index()
        .rename(columns={"BU (Inferido)": "BU"})
    )
    
    total_exp = resumen_bu["Log. Exp (USD)"].sum()
    resumen_bu["%PCT"] = resumen_bu["Log. Exp (USD)"] / total_exp if total_exp > 0 else 0.0
    resumen_bu = resumen_bu.sort_values("Log. Exp (USD)", ascending=False).reset_index(drop=True)
    
    # ─────────────────────────────────────────────────────────
    # 9. MÉTRICAS
    # ─────────────────────────────────────────────────────────
    num_referencias = referencias[columna_reference].nunique()
    
    # 🆕 Costo total esperado depende del modo
    if df_costos is not None and len(df_costos) > 0:
        # Suma de Fix Cost por reference única
        refs_en_datos = df[columna_reference].unique()
        df_costos_relevantes = df_costos[df_costos["Reference"].isin(refs_en_datos)]
        costo_total_esperado = df_costos_relevantes["Fix Cost"].sum()
        # Sumar también las refs sin costo (usando fallback)
        refs_con_fallback = [r for r in refs_en_datos if r not in df_costos_relevantes["Reference"].values]
        costo_total_esperado += len(refs_con_fallback) * costo_fijo
        modo_costo = "variable"
    else:
        costo_total_esperado = num_referencias * costo_fijo
        modo_costo = "fijo"
    
    costo_total_calculado = detalle["Calc_Exp"].sum()
    diferencia = abs(costo_total_esperado - costo_total_calculado)
    
    metricas = {
        "total_items": len(detalle),
        "total_references": num_referencias,
        "total_bus": len(bus_unicos),
        "bus_detectados": sorted(bus_unicos),
        "metodos_asignacion": metodos_count,
        "modo_costo": modo_costo,  # 🆕
        "costo_fijo_por_reference": costo_fijo if modo_costo == "fijo" else None,
        "costo_total_esperado": round(costo_total_esperado, 2),
        "costo_total_calculado": round(costo_total_calculado, 2),
        "diferencia_validacion": round(diferencia, 2),
        "validacion_ok": diferencia < 1.0,  # Tolerancia mayor por redondeos
        "filas_descartadas": filas_descartadas,
    }
    
    # ─────────────────────────────────────────────────────────
    # 10. LOG FINAL
    # ─────────────────────────────────────────────────────────
    logger.info("─" * 60)
    logger.info(f"✅ Items procesados:       {metricas['total_items']}")
    logger.info(f"✅ References únicos:      {metricas['total_references']}")
    logger.info(f"✅ BUs detectados:         {metricas['total_bus']} → {metricas['bus_detectados']}")
    logger.info(f"💰 Modo de costo:          {metricas['modo_costo'].upper()}")
    logger.info(f"💰 Costo total esperado:   ${metricas['costo_total_esperado']:,.2f}")
    logger.info(f"💰 Costo total calculado:  ${metricas['costo_total_calculado']:,.2f}")
    logger.info(f"🔍 Diferencia:             ${metricas['diferencia_validacion']:,.4f}")
    
    if metricas["validacion_ok"]:
        logger.info("✅ VALIDACIÓN: Conservación de costo OK")
    else:
        logger.warning(f"⚠️ Diferencia: ${metricas['diferencia_validacion']:.2f}")
    
    logger.info("=" * 60)
    
    return ResultadoOutbound(
        detalle=detalle,
        resumen_bu=resumen_bu,
        referencias=referencias,
        metricas=metricas,
        advertencias=advertencias,
    )
