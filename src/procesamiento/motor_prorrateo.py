"""
═══════════════════════════════════════════════════════════════
MOTOR DE PRORRATEO UNIFICADO
═══════════════════════════════════════════════════════════════
Una sola implementación que sirve para SEA, LAND y OUTBOUND.
Elimina duplicación de código entre procesar_sea/land/outbound.

Aplica la fórmula universal:
    Costo_item = (Peso_item / Peso_total_grupo) × Costo_fijo_grupo
═══════════════════════════════════════════════════════════════
"""
import pandas as pd
from typing import Optional, Dict, List
from dataclasses import dataclass, field

from src.utils.config_loader import get_config


@dataclass
class ResultadoProrrateo:
    detalle: pd.DataFrame                               # df con %Pond y Calc_Cost
    resumen_grupo: pd.DataFrame                         # un row por grupo
    resumen_bu: pd.DataFrame                            # un row por BU final
    metricas: Dict = field(default_factory=dict)
    advertencias: List[str] = field(default_factory=list)
    es_valido: bool = False


def prorratear(
    df: pd.DataFrame,
    operacion: str,
    columna_grupo: str,                                 # "Reference" | "Container" | "Waybill"
    columna_peso: str = "Gross_Weight",
    columna_bu: str = "BU",
    df_costos_variables: Optional[pd.DataFrame] = None, # opcional: Override por grupo
) -> ResultadoProrrateo:
    """
    Motor de prorrateo universal.

    Args:
        df: DataFrame con columnas canónicas (ya normalizadas)
        operacion: 'sea' | 'land' | 'outbound'
        columna_grupo: nombre de la columna que define el grupo
        columna_peso: nombre de la columna de peso
        columna_bu: nombre de la columna BU (asume YA inferido)
        df_costos_variables: DataFrame opcional con [grupo, Fix_Cost]

    Returns:
        ResultadoProrrateo con detalle + resumen + métricas + validación
    """
    config = get_config()
    costo_default = config.get_required(f"costos.{operacion}.valor")
    tolerancia = config.get("validaciones.tolerancia_costo", 0.01)
    decimales = config.get("validaciones.decimales_monto", 2)

    # ─────────────────────────────────────────────────────
    # 1. VALIDACIONES PRELIMINARES
    # ─────────────────────────────────────────────────────
    advertencias: List[str] = []
    for col in (columna_grupo, columna_peso, columna_bu):
        if col not in df.columns:
            raise ValueError(f"Columna '{col}' no existe en el df")

    df = df.copy()

    # Coerción numérica del peso
    df[columna_peso] = pd.to_numeric(df[columna_peso], errors="coerce")
    nulos_peso = df[columna_peso].isna().sum()
    if nulos_peso > 0:
        advertencias.append(
            f"⚠️ {nulos_peso} fila(s) con peso no numérico — convertidas a 0"
        )
        df[columna_peso] = df[columna_peso].fillna(0)

    # ─────────────────────────────────────────────────────
    # 2. ASIGNAR COSTO FIJO POR GRUPO (variable o default)
    # ─────────────────────────────────────────────────────
    df["_FixCost"] = costo_default

    if df_costos_variables is not None and len(df_costos_variables) > 0:
        # Espera columnas: [columna_grupo, "Fix_Cost"]
        if columna_grupo in df_costos_variables.columns \
                and "Fix_Cost" in df_costos_variables.columns:
            mapa_costos = dict(zip(
                df_costos_variables[columna_grupo].astype(str),
                df_costos_variables["Fix_Cost"],
            ))
            df["_FixCost"] = (
                df[columna_grupo].astype(str).map(mapa_costos)
                .fillna(costo_default)
            )

    # ─────────────────────────────────────────────────────
    # 3. CÁLCULO DE %POND Y CALC_COST (vectorizado)
    # ─────────────────────────────────────────────────────
    peso_por_grupo = df.groupby(columna_grupo)[columna_peso].transform("sum")

    # Evita división por cero
    peso_seguro = peso_por_grupo.replace(0, pd.NA)
    df["%Pond"] = (df[columna_peso] / peso_seguro).fillna(0)
    df["Calc_Cost"] = (df["%Pond"] * df["_FixCost"]).round(decimales)

    # ─────────────────────────────────────────────────────
    # 4. VALIDACIÓN POR GRUPO (cuadre vs costo fijo)
    # ─────────────────────────────────────────────────────
    cuadre = df.groupby(columna_grupo).agg(
        suma_calc=("Calc_Cost", "sum"),
        fix_cost=("_FixCost", "first"),
    )
    cuadre["diferencia"] = (cuadre["suma_calc"] - cuadre["fix_cost"]).abs()
    cuadre["cuadra"] = cuadre["diferencia"] <= tolerancia

    grupos_descuadrados = cuadre[~cuadre["cuadra"]]
    if len(grupos_descuadrados) > 0:
        advertencias.append(
            f"🔴 {len(grupos_descuadrados)} grupo(s) NO cuadran "
            f"(tolerancia ${tolerancia})"
        )

    # Marca de validación en el detalle
    df["Validacion"] = df[columna_grupo].map(
        lambda g: "🟢 OK" if cuadre.loc[g, "cuadra"] else "🔴 DIFF"
    )

    # ─────────────────────────────────────────────────────
    # 5. RESUMEN POR GRUPO
    # ─────────────────────────────────────────────────────
    resumen_grupo = df.groupby(columna_grupo).agg(
        n_items=(columna_peso, "size"),
        peso_total=(columna_peso, "sum"),
        costo_total=("Calc_Cost", "sum"),
        fix_cost=("_FixCost", "first"),
    ).reset_index()
    resumen_grupo["diferencia"] = (
        resumen_grupo["costo_total"] - resumen_grupo["fix_cost"]
    ).round(decimales)

    # ─────────────────────────────────────────────────────
    # 6. RESUMEN POR BU
    # ─────────────────────────────────────────────────────
    resumen_bu = df.groupby(columna_bu).agg(
        n_items=(columna_peso, "size"),
        peso_total=(columna_peso, "sum"),
        monto_total=("Calc_Cost", "sum"),
    ).reset_index()

    total_general = resumen_bu["monto_total"].sum()
    resumen_bu["%PCT"] = (
        resumen_bu["monto_total"] / total_general if total_general > 0 else 0
    )

    # ─────────────────────────────────────────────────────
    # 7. MÉTRICAS GLOBALES
    # ─────────────────────────────────────────────────────
    n_grupos = df[columna_grupo].nunique()
    costo_esperado = (
        cuadre["fix_cost"].sum()  # respeta costos variables
    )
    costo_calculado = df["Calc_Cost"].sum()
    diferencia_total = abs(costo_esperado - costo_calculado)

    metricas = {
        "operacion": operacion,
        "total_grupos": int(n_grupos),
        "total_items": int(len(df)),
        "total_bus": int(df[columna_bu].nunique()),
        "costo_total_esperado": float(costo_esperado),
        "costo_total_calculado": float(costo_calculado),
        "diferencia_total": float(diferencia_total),
        "validacion_ok": bool(diferencia_total <= tolerancia),
        "grupos_descuadrados": int(len(grupos_descuadrados)),
        "tolerancia_aplicada": float(tolerancia),
    }

    # Limpia columna interna
    df = df.drop(columns=["_FixCost"])

    return ResultadoProrrateo(
        detalle=df,
        resumen_grupo=resumen_grupo,
        resumen_bu=resumen_bu,
        metricas=metricas,
        advertencias=advertencias,
        es_valido=metricas["validacion_ok"],
    )