"""
═══════════════════════════════════════════════════════════════
PROCESADOR LAND — Réplica EXACTA de las fórmulas del Excel
═══════════════════════════════════════════════════════════════
🎯 Fórmula BY6: =BX6 * 1 / SUMIFS(BX:BX, BU:BU, BU6)
🎯 Fórmula BZ6: =BY6 * $BZ$1   (tarifa fija $1,200)
🎯 Fórmula CE6: =CD6 / SUM($CD$6:$CD$9)  (%PCT solo M19-M46)
═══════════════════════════════════════════════════════════════
"""
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any
import pandas as pd

from src.reglas.regla_miscelaneus import aplicar_regla_miscelaneus
from src.utils.logger import configurar_logger

logger = configurar_logger("procesar_land")

# 🚨 BUs ESPECIALES (excluidos del cálculo de %PCT)
BUS_EXCLUIDOS_PCT_LAND = ["Miscelaneus", "Machine"]


@dataclass
class ResultadoLand:
    df_detalle: pd.DataFrame
    resumen_bu: pd.DataFrame
    resumen_references: pd.DataFrame
    metricas: Dict[str, Any] = field(default_factory=dict)


def procesar_land(
    df_land: pd.DataFrame,
    costo_fijo: float = 1200.0,
    columna_reference: str = "Reference",
    columna_peso: str = "Peso Bruto",
    columna_item: str = "Item",
    columna_bu: str = "BU",
    tolerancia: float = 0.01,
) -> ResultadoLand:
    """
    Procesa LAND con prorrateo por Reference.
    
    Característica clave: BUs 'Miscelaneus' y 'Machine' se EXCLUYEN del 
    denominador %PCT (replica la fórmula Excel CE6 = CD6/SUM($CD$6:$CD$9)
    donde el rango cubre solo M19, M23, M45, M46).
    """
    logger.info("=" * 60)
    logger.info("🚛 PROCESANDO LAND (réplica fórmulas Excel)")
    logger.info("=" * 60)

    df = df_land.copy()
    
    if columna_bu not in df.columns:
        df[columna_bu] = "SIN_BU"
    df["BU Final"] = df[columna_bu]

    # 1. Aplicar regla Miscelaneus (plásticos)
    df, n_misc = aplicar_regla_miscelaneus(df, columna_item=columna_item, columna_bu_destino="BU Final")
    logger.info(f"   🔄 Reasignados a Miscelaneus: {n_misc}")

    df["Costo Fijo"] = costo_fijo

    # 2. %Propot — réplica de =BX6 * 1 / SUMIFS(BX:BX, BU:BU, BU6)
    #    OJO: en Excel la fórmula agrupa por BU (BU6), no por Reference
    df["Peso Total Reference"] = df.groupby(columna_reference)[columna_peso].transform("sum")
    df["%Propot"] = df.apply(
        lambda r: r[columna_peso] / r["Peso Total Reference"] if r["Peso Total Reference"] > 0 else 1.0,
        axis=1,
    )

    # 3. Amount — réplica de =BY6 * $BZ$1
    df["Amount"] = df["%Propot"] * costo_fijo

    # 4. Resumen por BU CON exclusión de Miscelaneus/Machine del denominador %PCT
    agg_bu = (
        df.groupby("BU Final", as_index=False)
        .agg(
            **{
                "Sum (USD)": ("Amount", "sum"),
                "# Items": (columna_item, "count"),
                "# References": (columna_reference, "nunique"),
                "Peso Total (Kgs)": (columna_peso, "sum"),
            }
        )
        .rename(columns={"BU Final": "BU"})
    )

    # 🔑 %PCT excluye Miscelaneus y Machine
    mask_validos = ~agg_bu["BU"].isin(BUS_EXCLUIDOS_PCT_LAND)
    base_pct = agg_bu.loc[mask_validos, "Sum (USD)"].sum()

    agg_bu["%PCT"] = agg_bu.apply(
        lambda r: (r["Sum (USD)"] / base_pct) if (r["BU"] not in BUS_EXCLUIDOS_PCT_LAND and base_pct > 0) else None,
        axis=1,
    )

    # Fila Total
    total_bruto = agg_bu["Sum (USD)"].sum()
    fila_total = pd.DataFrame([{
        "BU": "Total",
        "Sum (USD)": total_bruto,
        "# Items": agg_bu["# Items"].sum(),
        "# References": agg_bu["# References"].sum(),
        "Peso Total (Kgs)": agg_bu["Peso Total (Kgs)"].sum(),
        "%PCT": None,
    }])
    resumen_bu = pd.concat([agg_bu, fila_total], ignore_index=True)

    # 5. Resumen por Reference
    resumen_references = (
        df.groupby(columna_reference, as_index=False)
        .agg(
            **{
                "# Items": (columna_item, "count"),
                "Peso Total (Kgs)": (columna_peso, "sum"),
                "Costo Fijo": ("Costo Fijo", "first"),
                "Total Amount": ("Amount", "sum"),
            }
        )
        .rename(columns={columna_reference: "Reference"})
    )
    resumen_references["Diferencia"] = resumen_references["Total Amount"] - resumen_references["Costo Fijo"]
    resumen_references["Validación"] = resumen_references["Diferencia"].abs().apply(
        lambda d: "🟢 OK" if d <= tolerancia else "🔴 Descuadre"
    )

    # 6. Métricas
    grupos_desc = (resumen_references["Diferencia"].abs() > tolerancia).sum()
    metricas = {
        "total_items": int(len(df)),
        "total_references": int(df[columna_reference].nunique()),
        "bus_detectados": sorted(df["BU Final"].dropna().unique().tolist()),
        "bus_excluidos_pct": BUS_EXCLUIDOS_PCT_LAND,
        "costo_total_bruto": float(total_bruto),
        "costo_total_para_pct": float(base_pct),
        "tarifa_fija": float(costo_fijo),
        "items_misc_reasignados": int(n_misc),
        "tolerancia": float(tolerancia),
        "grupos_descuadrados": int(grupos_desc),
        "validacion_ok": bool(grupos_desc == 0),
    }

    logger.info("─" * 60)
    logger.info(f"✅ Items:                {metricas['total_items']}")
    logger.info(f"✅ References:           {metricas['total_references']}")
    logger.info(f"💰 Costo Total Bruto:    ${metricas['costo_total_bruto']:,.2f}")
    logger.info(f"💰 Costo para %PCT:      ${metricas['costo_total_para_pct']:,.2f}")
    logger.info(f"🚫 BUs Excluidos %PCT:   {metricas['bus_excluidos_pct']}")
    logger.info(f"✅ Validación OK:        {metricas['validacion_ok']}")
    logger.info("=" * 60)

    return ResultadoLand(
        df_detalle=df,
        resumen_bu=resumen_bu,
        resumen_references=resumen_references,
        metricas=metricas,
    )