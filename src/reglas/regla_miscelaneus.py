"""
═══════════════════════════════════════════════════════════════
REGLA MISCELANEUS — Reasignación de items plásticos
═══════════════════════════════════════════════════════════════
Aplica reglas de palabras clave para reclasificar items con
contenido plástico al BU "Miscelaneus".

Lee configuración desde config.yaml (NO hardcode).

🔑 LÓGICA:
  - palabras_sin_filtro:        SIEMPRE Miscelaneus (sin importar guion)
  - palabras_con_filtro_guion:  SOLO si NO hay guion antes (evita SKUs)

🔄 COMPATIBILIDAD HACIA ATRÁS:
  - cargar_config_miscelaneus() → para procesar_outbound/sea/land legacy
  - aplicar_regla_miscelaneus() → con firma extendida (params opcionales)
  - es_miscelaneus()            → API simple para tests
═══════════════════════════════════════════════════════════════
"""
import re
import pandas as pd
from typing import Optional, List, Tuple, Dict, Any

from src.utils.config_loader import get_config


# ════════════════════════════════════════════════════════════
# 🔄 COMPATIBILIDAD: cargar_config_miscelaneus()
# ════════════════════════════════════════════════════════════
def cargar_config_miscelaneus() -> Dict[str, Any]:
    """
    🔄 Compatibilidad con procesar_outbound/sea/land legacy.

    Lee la configuración de Miscelaneus desde config.yaml y retorna
    un dict listo para usar en aplicar_regla_miscelaneus().

    Returns:
        dict con:
        - palabras_sin_filtro:        list[str]
        - palabras_con_filtro_guion:  list[str]
        - bu_destino:                 str (default "Miscelaneus")
    """
    config = get_config()

    return {
        "palabras_sin_filtro": list(
            config.get("miscelaneus.palabras_sin_filtro", [])
        ),
        "palabras_con_filtro_guion": list(
            config.get("miscelaneus.palabras_con_filtro_guion", [])
        ),
        "bu_destino": config.get("miscelaneus.bu_destino", "Miscelaneus"),
    }


# ════════════════════════════════════════════════════════════
# FUNCIÓN CORE: ¿es_miscelaneus()?
# ════════════════════════════════════════════════════════════
def es_miscelaneus(
    descripcion,
    palabras_sin_filtro: Optional[List[str]] = None,
    palabras_con_filtro_guion: Optional[List[str]] = None,
) -> Tuple[bool, str]:
    """
    Determina si un item debe reclasificarse como Miscelaneus.

    Args:
        descripcion: Descripción o Item Code a evaluar
        palabras_sin_filtro: Si None, lee de config
        palabras_con_filtro_guion: Si None, lee de config

    Returns:
        (es_misc, razon)
    """
    if descripcion is None or pd.isna(descripcion):
        return False, "Descripción vacía"

    desc = str(descripcion).strip().upper()
    if not desc:
        return False, "Descripción vacía"

    # Cargar config si no se pasó como argumento
    if palabras_sin_filtro is None or palabras_con_filtro_guion is None:
        cfg = cargar_config_miscelaneus()
        if palabras_sin_filtro is None:
            palabras_sin_filtro = cfg["palabras_sin_filtro"]
        if palabras_con_filtro_guion is None:
            palabras_con_filtro_guion = cfg["palabras_con_filtro_guion"]

    # ────────────────────────────────────────────────────
    # NIVEL 1: palabras_sin_filtro (siempre match)
    # Ej: "BASE PLASTICA", "CAJAS PLASTICAS", "CHAROLA"
    # ────────────────────────────────────────────────────
    for palabra in palabras_sin_filtro:
        palabra_upper = str(palabra).strip().upper()
        if palabra_upper and palabra_upper in desc:
            return True, f"Match SIN_FILTRO: '{palabra_upper}'"

    # ────────────────────────────────────────────────────
    # NIVEL 2: palabras_con_filtro_guion
    # Solo match si NO está precedida por guion
    # Ej: "BASE PLASTICA" → Miscelaneus ✅
    #     "0070-PLASTIC-001" → NO (es parte del SKU)
    # ────────────────────────────────────────────────────
    for palabra in palabras_con_filtro_guion:
        palabra_upper = str(palabra).strip().upper()
        if not palabra_upper:
            continue
        # \b = límite de palabra | (?<!-) = NO precedida por guion
        patron = r"(?<!-)\b" + re.escape(palabra_upper) + r"\b"
        if re.search(patron, desc):
            return True, f"Match CON_FILTRO (sin guion): '{palabra_upper}'"

    return False, "No coincide con ninguna palabra clave"


# ════════════════════════════════════════════════════════════
# 🔄 FUNCIÓN PRINCIPAL: aplicar_regla_miscelaneus()
# ════════════════════════════════════════════════════════════
def aplicar_regla_miscelaneus(
    df: pd.DataFrame,
    columna_item: str = "Item",
    columna_descripcion: str = "Description",
    columna_bu_origen: str = "BU",
    columna_bu_destino: str = "BU Final",
    palabras_sin_filtro: Optional[List[str]] = None,
    palabras_con_filtro_guion: Optional[List[str]] = None,
    bu_miscelaneus: Optional[str] = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    🔄 Aplica la regla Miscelaneus a un DataFrame.

    Crea/actualiza la columna `columna_bu_destino` con:
      - "Miscelaneus" si el item coincide con palabras clave
      - El valor de `columna_bu_origen` en caso contrario

    Args:
        df: DataFrame a procesar
        columna_item: nombre de la columna Item Code (fallback)
        columna_descripcion: nombre de la columna de descripción
        columna_bu_origen: columna con el BU original (ej. "BU")
        columna_bu_destino: columna donde escribir el resultado (ej. "BU Final")
        palabras_sin_filtro: si None, lee de config.yaml
        palabras_con_filtro_guion: si None, lee de config.yaml
        bu_miscelaneus: nombre del BU destino (default "Miscelaneus")

    Returns:
        (df_modificado, reporte_dict)

        reporte_dict contiene:
        - items_reasignados:     int
        - monto_reasignado:      float (si hay columna 'Calc_Exp' o 'Amount')
        - bus_origen_reasignados: list[str] (BUs de origen únicos reasignados)
        - bu_destino:            str
        - detalle:               DataFrame con los items reasignados
    """
    # Cargar config si faltan parámetros
    if (
        palabras_sin_filtro is None
        or palabras_con_filtro_guion is None
        or bu_miscelaneus is None
    ):
        cfg = cargar_config_miscelaneus()
        if palabras_sin_filtro is None:
            palabras_sin_filtro = cfg["palabras_sin_filtro"]
        if palabras_con_filtro_guion is None:
            palabras_con_filtro_guion = cfg["palabras_con_filtro_guion"]
        if bu_miscelaneus is None:
            bu_miscelaneus = cfg["bu_destino"]

    df_resultado = df.copy()

    # ────────────────────────────────────────────────────
    # 1. Inicializar BU Destino con BU Origen
    # ────────────────────────────────────────────────────
    if columna_bu_origen in df_resultado.columns:
        df_resultado[columna_bu_destino] = df_resultado[columna_bu_origen]
    else:
        df_resultado[columna_bu_destino] = "Sin Asignar"

    # ────────────────────────────────────────────────────
    # 2. Evaluar fila por fila si es Miscelaneus
    # ────────────────────────────────────────────────────
    indices_reasignados = []
    razones = []

    for idx in df_resultado.index:
        # Buscar valor a evaluar: primero Description, luego Item
        valor_a_evaluar = None

        if columna_descripcion in df_resultado.columns:
            val_desc = df_resultado.at[idx, columna_descripcion]
            if val_desc is not None and not pd.isna(val_desc):
                valor_a_evaluar = val_desc

        if valor_a_evaluar is None and columna_item in df_resultado.columns:
            val_item = df_resultado.at[idx, columna_item]
            if val_item is not None and not pd.isna(val_item):
                valor_a_evaluar = val_item

        if valor_a_evaluar is None:
            continue

        es_misc, razon = es_miscelaneus(
            valor_a_evaluar,
            palabras_sin_filtro=palabras_sin_filtro,
            palabras_con_filtro_guion=palabras_con_filtro_guion,
        )

        if es_misc:
            df_resultado.at[idx, columna_bu_destino] = bu_miscelaneus
            indices_reasignados.append(idx)
            razones.append(razon)

    # ────────────────────────────────────────────────────
    # 3. Construir reporte
    # ────────────────────────────────────────────────────
    n_reasignados = len(indices_reasignados)

    # BUs origen únicos reasignados
    bus_origen_reasignados = []
    if n_reasignados > 0 and columna_bu_origen in df_resultado.columns:
        bus_origen_reasignados = sorted(
            df_resultado.loc[indices_reasignados, columna_bu_origen]
            .dropna()
            .astype(str)
            .unique()
            .tolist()
        )

    # Monto reasignado (si hay columna de monto)
    monto_reasignado = 0.0
    columna_monto = None
    for col_candidata in ("Calc_Exp", "Amount", "Monto", "Total"):
        if col_candidata in df_resultado.columns:
            columna_monto = col_candidata
            break

    if columna_monto and n_reasignados > 0:
        monto_reasignado = float(
            pd.to_numeric(
                df_resultado.loc[indices_reasignados, columna_monto],
                errors="coerce",
            ).fillna(0).sum()
        )

    # Detalle de items reasignados
    detalle = (
        df_resultado.loc[indices_reasignados].copy()
        if n_reasignados > 0
        else pd.DataFrame()
    )

    reporte = {
        "items_reasignados":      n_reasignados,
        "monto_reasignado":       round(monto_reasignado, 2),
        "bus_origen_reasignados": bus_origen_reasignados,
        "bu_destino":             bu_miscelaneus,
        "detalle":                detalle,
        "razones":                razones,
    }

    return df_resultado, reporte
