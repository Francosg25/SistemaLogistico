"""
═══════════════════════════════════════════════════════════════
PROCESADOR SEA — Réplica EXACTA de las fórmulas del Excel
═══════════════════════════════════════════════════════════════
🎯 Fórmula CR6: =IFERROR(CQ6/SUMIFS(CQ:CQ,CP:CP,CP6), 100%)
🎯 Fórmula CS6: =CR6 * $CS$2   (tarifa fija $2,500)
🎯 Fórmula CY7: =CX7 / $CX$13  (%PCT EXCLUYE Capex y MCS)
═══════════════════════════════════════════════════════════════
"""
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any
import pandas as pd

from src.utils.logger import configurar_logger

logger = configurar_logger("procesar_sea")

# 🚨 BUs ESPECIALES (excluidos del cálculo de %PCT)
BUS_EXCLUIDOS_PCT_SEA = ["Capex", "MCS"]


@dataclass
class ResultadoSea:
    df_detalle: pd.DataFrame
    resumen_bu: pd.DataFrame
    resumen_containers: pd.DataFrame
    metricas: Dict[str, Any] = field(default_factory=dict)


def procesar_sea(
    df_sea: pd.DataFrame,
    costo_fijo: float = 2500.0,
    columna_container: str = "Container",
    columna_peso: str = "Peso Bruto",
    columna_item: str = "Item",
    columna_bu: str = "BU",
    tolerancia: float = 0.01,
) -> ResultadoSea:
    """
    Procesa SEA con prorrateo por Container.
    
    Característica clave: BUs 'Capex' y 'MCS' se EXCLUYEN del denominador %PCT
    (replica la fórmula Excel CY7 = CX7/$CX$13 donde $CX$13 = SUM(CX7:CX12)
    y la lista CU empieza en M01, sin Capex/MCS).
    """
    logger.info("=" * 60)
    logger.info("🚢 PROCESANDO SEA (réplica fórmulas Excel)")
    logger.info("=" * 60)

    df = df_sea.copy()
    df["BU Final"] = df[columna_bu] if columna_bu in df.columns else "SIN_BU"
    df["Costo Fijo"] = costo_fijo

    # 1. %Pond — réplica de =CQ6/SUMIFS(CQ:CQ,CP:CP,CP6)
    df["Peso Total Container"] = df.groupby(columna_container)[columna_peso].transform("sum")
    df["%Pond"] = df.apply(
        lambda r: r[columna_peso] / r["Peso Total Container"] if r["Peso Total Container"] > 0 else 1.0,
        axis=1,
    )

    # 2. Cost — réplica de =CR6 * $CS$2
    df["Cost"] = df["%Pond"] * costo_fijo  # SIN round

    # 3. Resumen por BU CON exclusión de Capex/MCS del denominador %PCT
    agg_bu = (
        df.groupby("BU Final", as_index=False)
        .agg(
            **{
                "Amount (USD)": ("Cost", "sum"),
                "# Items": (columna_item, "count"),
                "# Containers": (columna_container, "nunique"),
                "Peso Total (Kgs)": (columna_peso, "sum"),
            }
        )
        .rename(columns={"BU Final": "BU"})
    )

    # 🔑 %PCT excluye Capex y MCS (idéntico a Excel: $CX$13 = SUM(CX7:CX12))
    mask_validos = ~agg_bu["BU"].isin(BUS_EXCLUIDOS_PCT_SEA)
    base_pct = agg_bu.loc[mask_validos, "Amount (USD)"].sum()

    agg_bu["%PCT"] = agg_bu.apply(
        lambda r: (r["Amount (USD)"] / base_pct) if (r["BU"] not in BUS_EXCLUIDOS_PCT_SEA and base_pct > 0) else None,
        axis=1,
    )
    agg_bu["New Amount"] = agg_bu.apply(
        lambda r: r["Amount (USD)"] if r["BU"] not in BUS_EXCLUIDOS_PCT_SEA else None,
        axis=1,
    )

    # Fila Total: distingue Total bruto vs Total para %PCT
    total_bruto = agg_bu["Amount (USD)"].sum()
    fila_total = pd.DataFrame([{
        "BU": "Total",
        "Amount (USD)": total_bruto,
        "# Items": agg_bu["# Items"].sum(),
        "# Containers": agg_bu["# Containers"].sum(),
        "Peso Total (Kgs)": agg_bu["Peso Total (Kgs)"].sum(),
        "%PCT": None,
        "New Amount": base_pct,  # solo M01-M46 (igual a Excel $CX$13)
    }])
    resumen_bu = pd.concat([agg_bu, fila_total], ignore_index=True)

    # 4. Resumen por Container
    resumen_containers = (
        df.groupby(columna_container, as_index=False)
        .agg(
            **{
                "# Items": (columna_item, "count"),
                "Peso Total (Kgs)": (columna_peso, "sum"),
                "Costo Fijo": ("Costo Fijo", "first"),
                "Total Cost": ("Cost", "sum"),
            }
        )
        .rename(columns={columna_container: "Container"})
    )
    resumen_containers["Diferencia"] = resumen_containers["Total Cost"] - resumen_containers["Costo Fijo"]
    resumen_containers["Validación"] = resumen_containers["Diferencia"].abs().apply(
        lambda d: "🟢 OK" if d <= tolerancia else "🔴 Descuadre"
    )

    # 5. Métricas
    grupos_desc = (resumen_containers["Diferencia"].abs() > tolerancia).sum()
    metricas = {
        "total_items": int(len(df)),
        "total_containers": int(df[columna_container].nunique()),
        "bus_detectados": sorted(df["BU Final"].dropna().unique().tolist()),
        "bus_excluidos_pct": BUS_EXCLUIDOS_PCT_SEA,
        "costo_total_bruto": float(total_bruto),
        "costo_total_para_pct": float(base_pct),
        "tarifa_fija": float(costo_fijo),
        "tolerancia": float(tolerancia),
        "grupos_descuadrados": int(grupos_desc),
        "validacion_ok": bool(grupos_desc == 0),
    }

    logger.info("─" * 60)
    logger.info(f"✅ Items:               {metricas['total_items']}")
    logger.info(f"✅ Containers:          {metricas['total_containers']}")
    logger.info(f"💰 Costo Total Bruto:   ${metricas['costo_total_bruto']:,.2f}")
    logger.info(f"💰 Costo para %PCT:     ${metricas['costo_total_para_pct']:,.2f}")
    logger.info(f"🚫 BUs Excluidos %PCT:  {metricas['bus_excluidos_pct']}")
    logger.info(f"✅ Validación OK:       {metricas['validacion_ok']}")
    logger.info("=" * 60)

    return ResultadoSea(
        df_detalle=df,
        resumen_bu=resumen_bu,
        resumen_containers=resumen_containers,
        metricas=metricas,
    )