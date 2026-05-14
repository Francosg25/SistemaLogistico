"""
═══════════════════════════════════════════════════════════════
REGLA MISCELANEUS - Reasignación de BU para items plásticos
═══════════════════════════════════════════════════════════════

Replica EXACTAMENTE la fórmula Excel:
    =IF(OR(
        ISNUMBER(SEARCH("PLASTIC", item)),
        ISNUMBER(SEARCH("CHAROLA", item)),
        AND(ISNUMBER(SEARCH("TAPA",  item)), NOT(ISNUMBER(SEARCH("-", item)))),
        AND(ISNUMBER(SEARCH("BASE",  item)), NOT(ISNUMBER(SEARCH("-", item)))),
        AND(ISNUMBER(SEARCH("CAJA",  item)), NOT(ISNUMBER(SEARCH("-", item))))
    ), "Miscelaneus", bu_original)

LÓGICA:
  • Si el nombre del item contiene "PLASTIC"  → Miscelaneus
  • Si el nombre del item contiene "CHAROLA"  → Miscelaneus
  • Si contiene "TAPA" Y NO contiene guion    → Miscelaneus
  • Si contiene "BASE" Y NO contiene guion    → Miscelaneus
  • Si contiene "CAJA" Y NO contiene guion    → Miscelaneus
  • Caso contrario                            → conservar BU original

El guion '-' funciona como filtro anti-falso-positivo:
  ✅ "BASE PLASTICA"      → Miscelaneus (sin guion, plástico)
  ✅ "CAJA CARTON"        → Miscelaneus (sin guion)
  ❌ "BASE-1200005"       → NO se reasigna (tiene guion, es código)
  ❌ "0070-1200005"       → NO se reasigna (es código de parte)
═══════════════════════════════════════════════════════════════
"""
import pandas as pd
from typing import List, Dict, Optional, Tuple
from src.utils.logger import configurar_logger

logger = configurar_logger("regla_miscelaneus")


# ════════════════════════════════════════════════════════════
# CONFIGURACIÓN DEFAULT (sobreescribible desde config.yaml)
# ════════════════════════════════════════════════════════════
PALABRAS_SIN_FILTRO = [
    "PLASTIC",   # cualquier item con PLASTIC (PLASTICA, PLASTICO, PLASTICS)
    "CHAROLA",   # CHAROLA PLASTICA, CHAROLAS, etc.
]

PALABRAS_CON_FILTRO_GUION = [
    "TAPA",      # TAPA PLASTICA → SÍ ; TAPA-1234 → NO
    "BASE",      # BASE PLASTICA → SÍ ; BASE-5678 → NO
    "CAJA",      # CAJAS PLASTICAS → SÍ ; CAJA-XYZ → NO
]

BU_DESTINO = "Miscelaneus"


# ════════════════════════════════════════════════════════════
# FUNCIONES PRINCIPALES
# ════════════════════════════════════════════════════════════
def es_item_miscelaneus(
    nombre_item: str,
    palabras_sin_filtro: List[str] = None,
    palabras_con_filtro_guion: List[str] = None,
) -> bool:
    """
    Determina si un item debe reasignarse a 'Miscelaneus'.

    Args:
        nombre_item: Nombre/descripción del item (ej: "BASE PLASTICA")
        palabras_sin_filtro: Lista de keywords que SIEMPRE reasignan
        palabras_con_filtro_guion: Keywords que solo reasignan SI NO hay guion

    Returns:
        True si debe reasignarse a Miscelaneus, False en caso contrario.

    Ejemplos:
        >>> es_item_miscelaneus("BASE PLASTICA")
        True
        >>> es_item_miscelaneus("0070-1200005")
        False
        >>> es_item_miscelaneus("TAPA-1234")
        False  # tiene guion
        >>> es_item_miscelaneus("CHAROLA PLASTICA")
        True
    """
    if not isinstance(nombre_item, str) or not nombre_item.strip():
        return False

    nombre_upper = nombre_item.upper()
    palabras_sin = palabras_sin_filtro or PALABRAS_SIN_FILTRO
    palabras_con = palabras_con_filtro_guion or PALABRAS_CON_FILTRO_GUION

    # Caso 1: palabras que SIEMPRE reasignan (PLASTIC, CHAROLA)
    for palabra in palabras_sin:
        if palabra.upper() in nombre_upper:
            return True

    # Caso 2: palabras que reasignan SOLO si no hay guion (TAPA, BASE, CAJA)
    tiene_guion = "-" in nombre_upper
    if not tiene_guion:
        for palabra in palabras_con:
            if palabra.upper() in nombre_upper:
                return True

    return False


def aplicar_regla_miscelaneus(
    df: pd.DataFrame,
    columna_item: str,
    columna_bu_origen: str = "BU",
    columna_bu_destino: str = "BU Final",
    palabras_sin_filtro: List[str] = None,
    palabras_con_filtro_guion: List[str] = None,
    bu_miscelaneus: str = BU_DESTINO,
) -> Tuple[pd.DataFrame, Dict]:
    """
    Aplica la regla Miscelaneus a un DataFrame y devuelve:
      1. El DataFrame con la nueva columna 'BU Final'
      2. Un reporte de auditoría con los items reasignados

    Args:
        df: DataFrame con datos
        columna_item: Nombre de la columna que tiene la descripción del item
                      (ej: "No. Parte Prov." en Land, "Item" en Outbound,
                       "Item Code" en Sea)
        columna_bu_origen: Columna del BU original (default: "BU")
        columna_bu_destino: Nombre de la columna nueva (default: "BU Final")
        palabras_sin_filtro: Keywords que siempre reasignan
        palabras_con_filtro_guion: Keywords que solo reasignan sin guion
        bu_miscelaneus: BU destino (default: "Miscelaneus")

    Returns:
        Tupla: (df_modificado, reporte_dict)

        reporte_dict contiene:
            - 'items_reasignados': int
            - 'monto_reasignado': float (si existe 'Calc_Exp' o 'Amount')
            - 'bus_origen_reasignados': List[str]
            - 'detalle': DataFrame con items reasignados
    """
    if df is None or len(df) == 0:
        return df, {"items_reasignados": 0, "detalle": pd.DataFrame()}

    if columna_item not in df.columns:
        logger.warning(
            f"⚠️ Columna '{columna_item}' no existe en el DataFrame. "
            f"Disponibles: {list(df.columns)}. Se omite regla Miscelaneus."
        )
        df[columna_bu_destino] = df.get(columna_bu_origen, "Sin BU")
        return df, {"items_reasignados": 0, "detalle": pd.DataFrame()}

    df = df.copy()

    # Aplicar la regla item por item (vectorizado con .apply)
    mascara_miscelaneus = df[columna_item].apply(
        lambda x: es_item_miscelaneus(x, palabras_sin_filtro, palabras_con_filtro_guion)
    )

    # Crear columna BU Final = BU Origen, excepto donde aplique la regla
    df[columna_bu_destino] = df[columna_bu_origen].copy()
    df.loc[mascara_miscelaneus, columna_bu_destino] = bu_miscelaneus

    # ════════════════════════════════════════════════════════
    # REPORTE DE AUDITORÍA
    # ════════════════════════════════════════════════════════
    items_reasignados = int(mascara_miscelaneus.sum())
    df_reasignados = df[mascara_miscelaneus].copy()

    # Calcular monto reasignado si existe alguna columna de monto
    monto_reasignado = 0.0
    columnas_monto_posibles = ["Calc_Exp", "Amount", "Monto", "Cost"]
    columna_monto_encontrada = None
    for col in columnas_monto_posibles:
        if col in df.columns:
            columna_monto_encontrada = col
            monto_reasignado = float(df.loc[mascara_miscelaneus, col].sum())
            break

    bus_origen = sorted(df_reasignados[columna_bu_origen].dropna().unique().tolist())

    reporte = {
        "items_reasignados": items_reasignados,
        "monto_reasignado": round(monto_reasignado, 2),
        "columna_monto_usada": columna_monto_encontrada,
        "bus_origen_reasignados": bus_origen,
        "bu_destino": bu_miscelaneus,
        "detalle": df_reasignados,
        "palabras_sin_filtro": palabras_sin_filtro or PALABRAS_SIN_FILTRO,
        "palabras_con_filtro_guion": palabras_con_filtro_guion or PALABRAS_CON_FILTRO_GUION,
    }

    # ════════════════════════════════════════════════════════
    # LOGGING
    # ════════════════════════════════════════════════════════
    if items_reasignados > 0:
        logger.info(
            f"🔄 Regla Miscelaneus aplicada: {items_reasignados} items reasignados "
            f"desde {bus_origen} → '{bu_miscelaneus}'"
        )
        if monto_reasignado > 0:
            logger.info(f"   💰 Monto reasignado: ${monto_reasignado:,.2f}")
    else:
        logger.info("✓ Regla Miscelaneus aplicada: 0 items afectados")

    return df, reporte


def cargar_config_miscelaneus() -> Dict:
    """
    Carga la configuración de Miscelaneus desde config.yaml si existe.
    Si no, usa los defaults definidos arriba.
    """
    try:
        from src.utils.config_loader import get_config
        config = get_config()

        palabras_sin = config.get("miscelaneus.palabras_sin_filtro", PALABRAS_SIN_FILTRO)
        palabras_con = config.get("miscelaneus.palabras_con_filtro_guion", PALABRAS_CON_FILTRO_GUION)
        bu_destino = config.get("miscelaneus.bu_destino", BU_DESTINO)

        return {
            "palabras_sin_filtro": palabras_sin,
            "palabras_con_filtro_guion": palabras_con,
            "bu_destino": bu_destino,
        }
    except Exception as e:
        logger.warning(f"No se pudo cargar config de Miscelaneus, usando defaults: {e}")
        return {
            "palabras_sin_filtro": PALABRAS_SIN_FILTRO,
            "palabras_con_filtro_guion": PALABRAS_CON_FILTRO_GUION,
            "bu_destino": BU_DESTINO,
        }