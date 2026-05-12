"""
Procesador de Importaciones Terrestres (LAND).

REGLAS DE NEGOCIO:
═══════════════════════════════════════════════════════════════
1. Agrupación:     Por 'Reference'
2. Costo Fijo:     $1,200 USD por Reference (parametrizable)
3. Cálculo:
   - %Pond = Peso_Item / Peso_Total_Reference
   - Cost  = %Pond × Costo_Fijo
4. BU:             Se toma DIRECTAMENTE de la columna BU del reporte
                   (NO se infiere como en Outbound)
5. BUs especiales: Además de M01, M19, M23, M45, M46, pueden aparecer:
                   - 'Machine'      (maquinaria)
                   - 'Miscelaneus'  (misceláneos: tapas, charolas, etc.)
                   Estos NO se excluyen del Summary (solo Capex/MCS de Sea)
═══════════════════════════════════════════════════════════════
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from dataclasses import dataclass, field

from src.utils.logger import configurar_logger

logger = configurar_logger("procesar_land")


# ============================================================
# BUs ESPECIALES CONOCIDOS (informativo, no obligatorio)
# ============================================================
# Lista de BUs especiales que NO siguen el patrón Mxx
# Se usan solo para clasificación visual y alertas
BUS_ESPECIALES_LAND = {"Machine", "Miscelaneus", "Miscellaneous"}


# ============================================================
# ESTRUCTURA DE RESULTADO
# ============================================================
@dataclass
class ResultadoLand:
    """Contenedor de resultados del procesamiento LAND."""
    detalle: pd.DataFrame                 # Cada item con su costo asignado
    resumen_bu: pd.DataFrame              # Resumen agrupado por BU
    resumen_referencias: pd.DataFrame     # Tabla de References con costo total
    metricas: Dict[str, any] = field(default_factory=dict)
    advertencias: List[str] = field(default_factory=list)


# ============================================================
# FUNCIÓN PRINCIPAL
# ============================================================
def procesar_land(
    df_land: pd.DataFrame,
    costo_fijo: float = 1200.0,
    columna_reference: str = "Reference",
    columna_bu: str = "BU",
    columna_peso: str = "Peso Bruto (Kgs)",
    columna_item: str = "No. Parte Prov.",
) -> ResultadoLand:
    """
    Procesa el reporte de importaciones terrestres aplicando todas las reglas.
    
    Args:
        df_land: DataFrame ya cargado y normalizado (output del Bloque 2)
        costo_fijo: Costo fijo por Reference (default $1,200 USD)
        columna_reference: Nombre de la columna Reference
        columna_bu: Nombre de la columna BU
        columna_peso: Nombre de la columna de peso bruto
        columna_item: Nombre de la columna del número de parte
    
    Returns:
        ResultadoLand con detalle, resumen_bu, resumen_referencias y métricas
    
    Raises:
        ValueError: Si faltan columnas o los datos son inválidos
    """
    logger.info("=" * 60)
    logger.info("🚚 INICIANDO PROCESAMIENTO LAND")
    logger.info("=" * 60)
    
    # ─────────────────────────────────────────────────────────
    # 1. VALIDACIONES INICIALES
    # ─────────────────────────────────────────────────────────
    if df_land is None or len(df_land) == 0:
        raise ValueError("El DataFrame de LAND está vacío.")
    
    columnas_req = [columna_reference, columna_bu, columna_peso, columna_item]
    faltantes = [c for c in columnas_req if c not in df_land.columns]
    if faltantes:
        raise ValueError(f"Faltan columnas obligatorias en LAND: {faltantes}")
    
    df = df_land.copy()
    advertencias = []
    
    logger.info(f"📊 Registros recibidos: {len(df)}")
    logger.info(f"💰 Costo fijo por Reference: ${costo_fijo:,.2f}")
    
    # ─────────────────────────────────────────────────────────
    # 2. LIMPIEZA: Eliminar filas inválidas
    # ─────────────────────────────────────────────────────────
    filas_antes = len(df)
    
    # Quitar filas sin Reference
    df = df.dropna(subset=[columna_reference])
    df = df[df[columna_reference].astype(str).str.strip() != ""]
    
    # Convertir peso a numérico y descartar inválidos
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
    # 3. VALIDAR BU (no inferimos, viene directo del reporte)
    # ─────────────────────────────────────────────────────────
    logger.info("🧠 Validando BUs del reporte...")
    
    # Detectar filas SIN BU asignado
    sin_bu = df[df[columna_bu].isna() | (df[columna_bu].astype(str).str.strip() == "")]
    if len(sin_bu) > 0:
        refs_sin_bu = sin_bu[columna_reference].unique().tolist()
        msg = (
            f"{len(sin_bu)} fila(s) sin BU asignado en {len(refs_sin_bu)} reference(s): "
            f"{refs_sin_bu[:5]}..."
        )
        advertencias.append(msg)
        logger.warning(f"⚠️ {msg}")
        # Asignar 'SinBU' para que no se pierdan en el agrupamiento
        df[columna_bu] = df[columna_bu].fillna("SinBU").replace("", "SinBU")
    
    # Detectar BUs especiales presentes
    bus_unicos = sorted(df[columna_bu].unique().tolist())
    bus_especiales_presentes = [bu for bu in bus_unicos if bu in BUS_ESPECIALES_LAND]
    bus_mxx = [bu for bu in bus_unicos if bu not in BUS_ESPECIALES_LAND and bu != "SinBU"]
    
    logger.info(f"   BUs estándar (Mxx):   {bus_mxx}")
    logger.info(f"   BUs especiales:        {bus_especiales_presentes}")
    
    # ─────────────────────────────────────────────────────────
    # 4. CÁLCULO DE %POND POR REFERENCE
    # ─────────────────────────────────────────────────────────
    logger.info("🧮 Calculando %Pond y Cost...")
    
    # Peso total por Reference (equivalente a SUMIFS en Excel)
    df["Peso Total Reference"] = df.groupby(columna_reference)[columna_peso].transform("sum")
    
    # %Pond = Peso_Item / Peso_Total_Reference
    df["%Pond"] = df[columna_peso] / df["Peso Total Reference"]
    df["%Pond"] = df["%Pond"].fillna(0)
    
    # Costo fijo por Reference
    df["Fix Cost"] = costo_fijo
    
    # Cost = %Pond × $1,200
    df["Cost"] = df["%Pond"] * df["Fix Cost"]
    
    # ─────────────────────────────────────────────────────────
    # 5. CONSTRUIR DETALLE FINAL
    # ─────────────────────────────────────────────────────────
    columnas_detalle = [
        col for col in [
            "Inbound/Outbound",
            "Method",
            columna_reference,
            columna_bu,
            columna_item,
            columna_peso,
            "Peso Total Reference",
            "%Pond",
            "Fix Cost",
            "Cost",
        ] if col in df.columns
    ]
    detalle = df[columnas_detalle].copy().reset_index(drop=True)
    
    # ─────────────────────────────────────────────────────────
    # 6. RESUMEN POR REFERENCE (1 fila por Reference)
    # ─────────────────────────────────────────────────────────
    resumen_referencias = (
        df.groupby(columna_reference)
        .agg(
            **{
                "# Items": (columna_item, "count"),
                "BUs Involucrados": (columna_bu, lambda x: ", ".join(sorted(x.unique()))),
                "Peso Total (Kgs)": (columna_peso, "sum"),
                "Fix Cost": ("Fix Cost", "first"),
                "Costo Total Calculado": ("Cost", "sum"),
            }
        )
        .reset_index()
    )
    
    # ─────────────────────────────────────────────────────────
    # 7. RESUMEN POR BU
    # ─────────────────────────────────────────────────────────
    resumen_bu = (
        df.groupby(columna_bu)
        .agg(
            **{
                "Monto Total (USD)": ("Cost", "sum"),
                "# References": (columna_reference, "nunique"),
                "# Items": (columna_item, "count"),
                "Peso Total (Kgs)": (columna_peso, "sum"),
            }
        )
        .reset_index()
        .rename(columns={columna_bu: "BU"})
    )
    
    # Calcular %PCT del total
    total_amount = resumen_bu["Monto Total (USD)"].sum()
    if total_amount > 0:
        resumen_bu["%PCT"] = resumen_bu["Monto Total (USD)"] / total_amount
    else:
        resumen_bu["%PCT"] = 0.0
    
    # Marcar BUs especiales para la UI
    resumen_bu["Tipo BU"] = resumen_bu["BU"].apply(
        lambda x: "Especial" if x in BUS_ESPECIALES_LAND 
        else ("Sin asignar" if x == "SinBU" else "Estándar")
    )
    
    # Ordenar de mayor a menor monto
    resumen_bu = resumen_bu.sort_values("Monto Total (USD)", ascending=False).reset_index(drop=True)
    
    # ─────────────────────────────────────────────────────────
    # 8. MÉTRICAS Y VALIDACIONES
    # ─────────────────────────────────────────────────────────
    num_referencias = resumen_referencias[columna_reference].nunique()
    costo_total_esperado = num_referencias * costo_fijo
    costo_total_calculado = detalle["Cost"].sum()
    diferencia = abs(costo_total_esperado - costo_total_calculado)
    
    metricas = {
        "total_items": len(detalle),
        "total_references": num_referencias,
        "total_bus": len(bus_unicos),
        "bus_detectados": bus_unicos,
        "bus_estandar": bus_mxx,
        "bus_especiales": bus_especiales_presentes,
        "costo_fijo_por_reference": costo_fijo,
        "costo_total_esperado": costo_total_esperado,
        "costo_total_calculado": round(costo_total_calculado, 2),
        "diferencia_validacion": round(diferencia, 2),
        "validacion_ok": diferencia < 0.01,
        "filas_descartadas": filas_descartadas,
        "peso_total_kgs": round(detalle[columna_peso].sum(), 2),
    }
    
    # ─────────────────────────────────────────────────────────
    # 9. LOG FINAL
    # ─────────────────────────────────────────────────────────
    logger.info("─" * 60)
    logger.info(f"✅ Items procesados:       {metricas['total_items']}")
    logger.info(f"✅ References únicas:      {metricas['total_references']}")
    logger.info(f"✅ BUs detectados:         {metricas['total_bus']} → {bus_unicos}")
    logger.info(f"💰 Costo total esperado:   ${metricas['costo_total_esperado']:,.2f}")
    logger.info(f"💰 Costo total calculado:  ${metricas['costo_total_calculado']:,.2f}")
    logger.info(f"⚖️  Peso total:             {metricas['peso_total_kgs']:,.2f} Kgs")
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
    
    return ResultadoLand(
        detalle=detalle,
        resumen_bu=resumen_bu,
        resumen_referencias=resumen_referencias,
        metricas=metricas,
        advertencias=advertencias,
    )


# ============================================================
# FÓRMULAS EXCEL EQUIVALENTES (para Bloque 9)
# ============================================================
def obtener_formulas_excel() -> Dict[str, str]:
    """
    Retorna las fórmulas Excel equivalentes a los cálculos hechos en Python.
    Se usarán en la generación del Excel de salida para que el usuario
    pueda auditar los cálculos directamente.
    """
    return {
        "peso_total_reference": (
            '=SUMIFS([Peso Bruto (Kgs)], [Reference], [@Reference])'
        ),
        "pct_pond": (
            '=[@[Peso Bruto (Kgs)]] / '
            'SUMIFS([Peso Bruto (Kgs)], [Reference], [@Reference])'
        ),
        "cost": (
            '=[@[%Pond]] * 1200'
        ),
        "monto_total_bu": (
            '=SUMIFS([Cost], [BU], [@BU])'
        ),
        "pct_bu": (
            '=[@[Monto Total (USD)]] / SUM([Monto Total (USD)])'
        ),
        "costo_total_reference": (
            '=SUMIFS([Cost], [Reference], [@Reference])'
        ),
    }