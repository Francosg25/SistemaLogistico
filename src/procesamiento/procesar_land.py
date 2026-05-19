"""
═══════════════════════════════════════════════════════════════
PROCESADOR LAND (Importaciones terrestres)
═══════════════════════════════════════════════════════════════
ORDEN DE OPERACIONES (CRÍTICO):
  1. Limpieza
  2. Inferir BU si falta
  3. 🔄 Aplicar regla Miscelaneus → crea 'BU Final'
  4. Calcular %Proporción y Amount
  5. Agrupar por 'BU Final'
═══════════════════════════════════════════════════════════════
"""
import pandas as pd
import numpy as np
import re
from typing import Dict, Optional
from dataclasses import dataclass, field

from src.reglas.inferencia_bu import inferir_bu_desde_reference
from src.reglas.regla_miscelaneus import (
    aplicar_regla_miscelaneus,
    cargar_config_miscelaneus,
)
from src.utils.logger import configurar_logger

logger = configurar_logger("procesar_land")


@dataclass
class ResultadoLand:
    detalle: pd.DataFrame
    resumen_bu: pd.DataFrame
    resumen_referencias: pd.DataFrame
    metricas: Dict[str, any] = field(default_factory=dict)
    advertencias: list = field(default_factory=list)
    reporte_miscelaneus: Dict = field(default_factory=dict)



def _inferir_bu_desde_referencia(referencia: str) -> str:
    """
    Extrae el BU del campo 'Referencia' en archivos LAND.
    
    Regla LAND (diferente a Outbound):
      • Buscar el PRIMER patrón Mxx (M seguido de 2 dígitos) en la referencia
      • Ignorar sufijos después del punto o guion
      • Si no encuentra → 'SIN_BU'
    
    Examples:
      'RM-J-1359LI26-M23.CS1037' → 'M23'  (primer match)
      'RM-J-1361LI26-M19'        → 'M19'  (primer match)
      'RM-J-1377LI26-M19.2'      → 'M19'  (ignora .2)
      'RM-J-1381LI26-M00'        → 'M00'  (M00 es válido)
      'RM-J-1390LI26-M23'        → 'M23'  (primer match)
    """
    if not isinstance(referencia, str):
        return "SIN_BU"
    
    # Buscar el primer patrón Mxx (M seguido de 2 dígitos)
    match = re.search(r'M\d{2}', referencia.upper())
    
    if match:
        return match.group(0)
    return "SIN_BU"




def procesar_land(
    df_land: pd.DataFrame,
    costo_fijo: float = 1200.0,
    columna_reference: str = "Reference",
    columna_peso: str = "Peso Bruto",       # 🔧 NOMBRE LÓGICO (nuevo lector)
    columna_item: str = "Item",              # 🔧 NOMBRE LÓGICO (nuevo lector)
    columna_bu: str = "BU",
) -> ResultadoLand:
    """
    Procesa el reporte LAND aplicando prorrateo + regla Miscelaneus.
    """
    logger.info("=" * 60)
    logger.info("🚛 INICIANDO PROCESAMIENTO LAND")
    logger.info("=" * 60)
    
    if df_land is None or len(df_land) == 0:
        raise ValueError("El DataFrame de Land está vacío.")
    
    df = df_land.copy()
    
   
    columna_referencia = "Reference"  # nombre lógico mapeado
    columna_bu = "BU"
    
    if columna_bu not in df.columns:
        logger.info("   🧠 Columna 'BU' no existe → infiriendo desde 'Referencia' (regex Mxx)")
        if columna_referencia in df.columns:
            df[columna_bu] = df[columna_referencia].apply(_inferir_bu_desde_referencia)
            bus_inferidos = sorted(df[columna_bu].dropna().unique().tolist())
            logger.info(f"   ✅ BUs inferidos: {bus_inferidos}")
        else:
            raise ValueError(
                "No se puede inferir BU: falta también la columna 'Referencia/Reference'"
            )
    else:
        # Si existe pero tiene nulos, inferir solo los faltantes
        mask_nulos = (
            df[columna_bu].isna()
            | (df[columna_bu].astype(str).str.strip() == "")
        )
        if mask_nulos.any() and columna_referencia in df.columns:
            n_nulos = mask_nulos.sum()
            logger.info(f"   🧠 Infiriendo BU para {n_nulos} filas con BU vacío")
            df.loc[mask_nulos, columna_bu] = df.loc[mask_nulos, columna_referencia].apply(
                _inferir_bu_desde_referencia
            )
    
    # Fallback final
    df[columna_bu] = df[columna_bu].fillna("Sin Asignar")
    df.loc[df[columna_bu].astype(str).str.strip() == "", columna_bu] = "Sin Asignar"
    
    advertencias = []
    
    # ─────────────────────────────────────────────────────────
    # COMPATIBILIDAD: aceptar nombres viejos si llegan
    # ─────────────────────────────────────────────────────────
    # Si viene 'Peso Bruto (Kgs)' pero no 'Peso Bruto', renombrar
    if "Peso Bruto" not in df.columns and "Peso Bruto (Kgs)" in df.columns:
        df["Peso Bruto"] = df["Peso Bruto (Kgs)"]
    if "Item" not in df.columns and "No. Parte Prov." in df.columns:
        df["Item"] = df["No. Parte Prov."]
    
    logger.info(f"📊 Registros recibidos: {len(df)}")
    logger.info(f"   Columnas disponibles: {list(df.columns)[:15]}...")


    
    
    # ─────────────────────────────────────────────────────────
    # PASO 1: LIMPIEZA
    # ─────────────────────────────────────────────────────────
    filas_antes = len(df)
    df = df.dropna(subset=[columna_reference])
    df = df[df[columna_reference].astype(str).str.strip() != ""]
    df[columna_peso] = pd.to_numeric(df[columna_peso], errors="coerce")
    df = df.dropna(subset=[columna_peso])
    df = df[df[columna_peso] > 0]
    
    filas_descartadas = filas_antes - len(df)
    if filas_descartadas > 0:
        msg = f"Se descartaron {filas_descartadas} filas (sin Reference o peso inválido)"
        advertencias.append(msg)
        logger.warning(f"⚠️ {msg}")
    
    if len(df) == 0:
        raise ValueError(
            "Todos los registros de LAND fueron descartados. "
            "Verifica que las columnas Reference, Peso Bruto e Item existan y tengan datos."
        )
    
    # ─────────────────────────────────────────────────────────
    # PASO 2: ASEGURAR QUE EXISTA COLUMNA 'BU' (inferir si falta)
    # ─────────────────────────────────────────────────────────
    if columna_bu not in df.columns:
        logger.info("   ℹ️ Columna 'BU' no existe en archivo - infiriendo del Reference")
        df[columna_bu] = df[columna_reference].apply(inferir_bu_desde_reference)
    else:
        # Si existe pero tiene nulos, intentar inferir
        mask_nulos = df[columna_bu].isna() | (df[columna_bu].astype(str).str.strip() == "")
        if mask_nulos.any():
            logger.info(f"   ℹ️ Infiriendo BU para {mask_nulos.sum()} filas con BU nulo")
            df.loc[mask_nulos, columna_bu] = df.loc[mask_nulos, columna_reference].apply(
                inferir_bu_desde_reference
            )
    
    # Si después de inferir aún hay nulos, marcar como 'Sin Asignar'
    df[columna_bu] = df[columna_bu].fillna("Sin Asignar")
    df.loc[df[columna_bu].astype(str).str.strip() == "", columna_bu] = "Sin Asignar"
    
    bus_originales = sorted(df[columna_bu].dropna().unique().tolist())
    logger.info(f"   ✅ BUs originales detectados: {bus_originales}")
    
    # ─────────────────────────────────────────────────────────
    # PASO 3: 🔄 APLICAR REGLA MISCELANEUS (CREA 'BU Final')
    # ─────────────────────────────────────────────────────────
    logger.info("🔄 Aplicando regla Miscelaneus...")
    
    config_misc = cargar_config_miscelaneus()
    df, reporte_miscelaneus = aplicar_regla_miscelaneus(
        df,
        columna_item=columna_item,            # 'Item'
        columna_bu_origen=columna_bu,         # 'BU'
        columna_bu_destino="BU Final",        # 🆕 ESTA SE CREA
        palabras_sin_filtro=config_misc["palabras_sin_filtro"],
        palabras_con_filtro_guion=config_misc["palabras_con_filtro_guion"],
        bu_miscelaneus=config_misc["bu_destino"],
    )
    
    # Verificación defensiva: si por alguna razón no se creó 'BU Final', crearla
    if "BU Final" not in df.columns:
        logger.warning("⚠️ 'BU Final' no se creó. Copiando desde 'BU' como fallback.")
        df["BU Final"] = df[columna_bu]
    
    if reporte_miscelaneus.get("items_reasignados", 0) > 0:
        logger.info(
            f"   ✅ {reporte_miscelaneus['items_reasignados']} items reasignados a "
            f"'{reporte_miscelaneus['bu_destino']}'"
        )
    
    # ─────────────────────────────────────────────────────────
    # PASO 4: CALCULAR %PROPORCIÓN Y AMOUNT
    # ─────────────────────────────────────────────────────────
    logger.info("🧮 Calculando %Proporción y Amount...")
    
    df["Peso Total Reference"] = df.groupby(columna_reference)[columna_peso].transform("sum")
    df["%Proporcion"] = df[columna_peso] / df["Peso Total Reference"]
    df["%Proporcion"] = df["%Proporcion"].fillna(0)
    df["Fix Cost"] = costo_fijo
    df["Amount"] = df["%Proporcion"] * df["Fix Cost"]
    
    # ─────────────────────────────────────────────────────────
    # PASO 5: RESUMEN POR BU (USANDO 'BU Final')
    # ─────────────────────────────────────────────────────────
    logger.info("📊 Generando resumen por BU Final...")
    
    resumen_bu = (
        df.groupby("BU Final")  # 🔧 Ahora SÍ existe
        .agg(
            **{
                "Monto Total (USD)": ("Amount", "sum"),
                "# References":      (columna_reference, "nunique"),
                "# Items":           (columna_item, "count"),
                "Peso Total (Kgs)":  (columna_peso, "sum"),
            }
        )
        .reset_index()
        .rename(columns={"BU Final": "BU"})
    )
    
    total_monto = resumen_bu["Monto Total (USD)"].sum()
    resumen_bu["%PCT"] = (
        (resumen_bu["Monto Total (USD)"] / total_monto * 100) if total_monto > 0 else 0.0
    )
    resumen_bu = resumen_bu.sort_values("Monto Total (USD)", ascending=False).reset_index(drop=True)
    
    # ─────────────────────────────────────────────────────────
    # PASO 6: RESUMEN POR REFERENCE
    # ─────────────────────────────────────────────────────────
    resumen_referencias = (
        df.groupby(columna_reference)
        .agg(
            **{
                "BU Asignado":      ("BU Final", lambda x: x.mode().iloc[0] if len(x.mode()) > 0 else "Sin Asignar"),
                "# Items":          (columna_item, "count"),
                "Peso Total (Kgs)": (columna_peso, "sum"),
                "Fix Cost":         ("Fix Cost", "first"),
                "Total Amount":     ("Amount", "sum"),
            }
        )
        .reset_index()
    )
    
    # ─────────────────────────────────────────────────────────
    # PASO 7: MÉTRICAS
    # ─────────────────────────────────────────────────────────
    num_refs = resumen_referencias[columna_reference].nunique()
    costo_esperado = num_refs * costo_fijo
    costo_calculado = df["Amount"].sum()
    diferencia = abs(costo_esperado - costo_calculado)
    
    metricas = {
        "total_items": len(df),
        "total_references": num_refs,
        "total_bus": len(resumen_bu),
        "bus_detectados": resumen_bu["BU"].tolist(),
        "costo_fijo_por_reference": costo_fijo,
        "costo_total_esperado": round(costo_esperado, 2),
        "costo_total_calculado": round(costo_calculado, 2),
        "diferencia_validacion": round(diferencia, 2),
        "validacion_ok": diferencia < 1.0,
        "filas_descartadas": filas_descartadas,
        # 🆕 Compatibilidad con pestaña Land
        "bus_especiales": [
            bu for bu in resumen_bu["BU"].tolist()
            if bu in ("Miscelaneus", "Machine", "Capex", "MCS", "Sin Asignar")
        ],
        "bus_nuevos": [],
        "miscelaneus": {
            "items_reasignados": reporte_miscelaneus.get("items_reasignados", 0),
            "monto_reasignado": reporte_miscelaneus.get("monto_reasignado", 0.0),
            "bus_origen": reporte_miscelaneus.get("bus_origen_reasignados", []),
        },
    }
    
    # ─────────────────────────────────────────────────────────
    # PASO 8: LOG FINAL
    # ─────────────────────────────────────────────────────────
    logger.info("─" * 60)
    logger.info(f"✅ Items procesados:       {metricas['total_items']}")
    logger.info(f"✅ References únicas:      {metricas['total_references']}")
    logger.info(f"✅ BUs en resumen:         {metricas['total_bus']} → {metricas['bus_detectados']}")
    logger.info(f"💰 Costo esperado:         ${metricas['costo_total_esperado']:,.2f}")
    logger.info(f"💰 Costo calculado:        ${metricas['costo_total_calculado']:,.2f}")
    logger.info(f"🔄 Items reasignados:      {metricas['miscelaneus']['items_reasignados']}")
    logger.info("=" * 60)
    
    return ResultadoLand(
        detalle=df,
        resumen_bu=resumen_bu,
        resumen_referencias=resumen_referencias,
        metricas=metricas,
        advertencias=advertencias,
        reporte_miscelaneus=reporte_miscelaneus,
    )