"""
═══════════════════════════════════════════════════════════════
INFERIR BU SEA — Auto-detección de Business Unit
═══════════════════════════════════════════════════════════════
Aplica un mapa Item Code → BU embebido en src/config/maestro_bu_sea.json.

Estrategia en cascada:
  1. Match exacto por Item Code (95%+ de casos)
  2. Fallback por Subinventory (si Item es nuevo)
  3. Marcar como 'SIN_BU' (warning para mantenimiento)
═══════════════════════════════════════════════════════════════
"""
import json
import pandas as pd
from pathlib import Path
from typing import Dict, Tuple

from src.utils.logger import configurar_logger

logger = configurar_logger("inferir_bu_sea")

RUTA_MAESTRO = Path(__file__).parent.parent / "config" / "maestro_bu_sea.json"


def cargar_maestro_bu_sea() -> Tuple[Dict[str, str], Dict[str, str]]:
    """Carga el maestro Item Code → BU desde el JSON embebido."""
    if not RUTA_MAESTRO.exists():
        logger.warning(
            f"⚠️ Maestro no encontrado en {RUTA_MAESTRO}. "
            f"Ejecuta scripts/generar_maestro_bu_sea.py para generarlo."
        )
        return {}, {}
    
    try:
        with open(RUTA_MAESTRO, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        mapa_items = data.get("mapa_item_code_a_bu", {})
        mapa_subinv = data.get("mapa_subinventory_a_bu", {})
        
        logger.info(
            f"📚 MAESTRO_BU_SEA cargado: "
            f"{len(mapa_items)} items + {len(mapa_subinv)} subinventories"
        )
        return mapa_items, mapa_subinv
    
    except Exception as e:
        logger.error(f"❌ Error cargando maestro: {e}")
        return {}, {}


def inferir_bu_sea(
    df: pd.DataFrame,
    columna_item: str = "Item Code",
    columna_subinv: str = "Subinventory",
    columna_bu_destino: str = "BU",
    sobrescribir: bool = False,
) -> Tuple[pd.DataFrame, Dict]:
    """
    Auto-infiere la columna BU en un DataFrame de Sea.
    
    Returns:
        (df_modificado, reporte) — reporte tiene métricas detalladas
    """
    logger.info("=" * 60)
    logger.info("🧠 INFIRIENDO BU DESDE MAESTRO_BU_SEA")
    logger.info("=" * 60)
    
    df = df.copy()
    mapa_items, mapa_subinv = cargar_maestro_bu_sea()
    
    if not mapa_items:
        logger.warning("   ⚠️ Maestro vacío. No se puede inferir BU.")
        if columna_bu_destino not in df.columns:
            df[columna_bu_destino] = "SIN_BU"
        return df, {"items_total": len(df), "sin_bu": len(df)}
    
    # Estado inicial
    if columna_bu_destino not in df.columns:
        logger.info(f"   ℹ️ Columna '{columna_bu_destino}' NO existe. Se creará.")
        df[columna_bu_destino] = None
    else:
        logger.info(f"   ℹ️ Columna '{columna_bu_destino}' YA existe.")
    
    mask_vacio = (
        df[columna_bu_destino].isna()
        | (df[columna_bu_destino].astype(str).str.strip().isin(["", "nan", "None"]))
    )
    
    if sobrescribir:
        mask_a_inferir = pd.Series([True] * len(df), index=df.index)
    else:
        mask_a_inferir = mask_vacio
    
    n_existente = int((~mask_vacio).sum()) if not sobrescribir else 0
    logger.info(
        f"   📊 {n_existente} filas con BU existente | "
        f"{mask_a_inferir.sum()} filas a inferir"
    )
    
    # Validar columna Item
    if columna_item not in df.columns:
        logger.error(
            f"   🚨 Columna '{columna_item}' no existe. "
            f"Columnas disponibles: {list(df.columns)[:20]}"
        )
        df.loc[mask_a_inferir, columna_bu_destino] = "SIN_BU"
        return df, {
            "items_total": len(df),
            "sin_bu": int(mask_a_inferir.sum()),
            "error": f"Columna '{columna_item}' no encontrada",
        }
    
    tiene_subinv = columna_subinv in df.columns
    
    def _buscar_bu(row) -> str:
        item = str(row.get(columna_item, "")).strip()
        if item in mapa_items:
            return mapa_items[item]
        
        if tiene_subinv:
            subinv = str(row.get(columna_subinv, "")).strip()
            if subinv in mapa_subinv:
                return mapa_subinv[subinv]
        
        return "SIN_BU"
    
    # Aplicar inferencia
    df_a_inferir = df[mask_a_inferir].copy()
    if len(df_a_inferir) > 0:
        bus_inferidos = df_a_inferir.apply(_buscar_bu, axis=1)
        df.loc[mask_a_inferir, columna_bu_destino] = bus_inferidos.values
    
    # Métricas detalladas
    n_por_item = 0
    n_por_subinv = 0
    n_sin_bu = 0
    items_sin_bu = []
    
    for idx in df_a_inferir.index:
        item = str(df.at[idx, columna_item]).strip()
        if item in mapa_items:
            n_por_item += 1
        elif tiene_subinv:
            subinv = str(df.at[idx, columna_subinv]).strip()
            if subinv in mapa_subinv:
                n_por_subinv += 1
            else:
                n_sin_bu += 1
                items_sin_bu.append(item)
        else:
            n_sin_bu += 1
            items_sin_bu.append(item)
    
    items_sin_bu_unicos = sorted(set(items_sin_bu))
    
    logger.info(f"   ✅ Matcheo por Item Code:    {n_por_item}")
    logger.info(f"   ✅ Matcheo por Subinventory: {n_por_subinv}")
    logger.info(f"   ⚠️ Sin BU asignado:          {n_sin_bu}")
    
    if items_sin_bu_unicos:
        muestra = items_sin_bu_unicos[:5]
        logger.warning(
            f"   🚨 Item Codes NUEVOS no mapeados: {len(items_sin_bu_unicos)} únicos. "
            f"Muestra: {muestra}"
        )
        logger.warning(
            f"   📝 Agrega estos items a MAESTRO_BU_SEA y regenera el JSON."
        )
    
    bus_finales = sorted(df[columna_bu_destino].dropna().unique().tolist())
    logger.info(f"   📊 BUs finales en df: {bus_finales}")
    logger.info("=" * 60)
    
    reporte = {
        "items_total":          len(df),
        "bu_existente":         n_existente,
        "bu_por_item_code":     n_por_item,
        "bu_por_subinventory":  n_por_subinv,
        "sin_bu":               n_sin_bu,
        "item_codes_sin_bu":    items_sin_bu_unicos,
        "bus_finales":          bus_finales,
        "cobertura_pct":        round(
            ((n_por_item + n_por_subinv) / max(mask_a_inferir.sum(), 1)) * 100, 1
        ),
    }
    
    return df, reporte