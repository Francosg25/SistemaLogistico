"""
═══════════════════════════════════════════════════════════════
INFERIDOR DE BU — Cascada Determinística de 4 Niveles
═══════════════════════════════════════════════════════════════
🧠 Estrategia universal para SEA / LAND / OUTBOUND:

  1️⃣ NIVEL 1: Item Code → BU (MAESTRO_BU_SEA.json)
  2️⃣ NIVEL 2: Subinventory → BU (si nivel 1 falla)
  3️⃣ NIVEL 3: Regex sobre Waybill/Reference (/M\\d{2}/)
  4️⃣ NIVEL 4: Regla Miscelaneus o SIN_BU

🎯 Reglas especiales:
  - OUTBOUND: si hay 2+ BUs en Reference → usar EL ÚLTIMO
  - SEA/LAND: si hay 2+ BUs en Reference → usar EL PRIMERO
  - AMBIGUO en Subinventory → bajar a nivel 3
═══════════════════════════════════════════════════════════════
"""
import re
import json
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from functools import lru_cache

from src.utils.config_loader import get_config
from src.reglas.regla_miscelaneus import es_miscelaneus


# ════════════════════════════════════════════════════════════
# REPORTE DE INFERENCIA
# ════════════════════════════════════════════════════════════
@dataclass
class ReporteInferencia:
    """Métricas detalladas de la inferencia de BU."""
    total_items: int = 0
    nivel_1_item_code: int = 0           # Match por MAESTRO_BU_SEA
    nivel_2_subinventory: int = 0        # Match por Subinventory
    nivel_3_regex: int = 0               # Match por patrón regex
    nivel_4_miscelaneus: int = 0         # Reclasificado como Miscelaneus
    nivel_4_sin_bu: int = 0              # No se pudo clasificar
    bus_finales: Dict[str, int] = field(default_factory=dict)
    items_sin_bu: List[str] = field(default_factory=list)
    ambiguos_resueltos: int = 0          # AMBIGUO bajados al siguiente nivel

    @property
    def cobertura_pct(self) -> float:
        if self.total_items == 0:
            return 0.0
        resueltos = (
            self.nivel_1_item_code
            + self.nivel_2_subinventory
            + self.nivel_3_regex
            + self.nivel_4_miscelaneus
        )
        return round(resueltos / self.total_items * 100, 2)


# ════════════════════════════════════════════════════════════
# CARGA DEL MAESTRO (con cache)
# ════════════════════════════════════════════════════════════
@lru_cache(maxsize=1)
def cargar_maestro_bu() -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    Carga MAESTRO_BU_SEA.json (cached).

    Returns:
        (mapa_items, mapa_subinventories)
    """
    config = get_config()
    ruta = config.get("rutas.maestro_bu_sea", "src/config/maestro_bu_sea.json")
    path = Path(ruta)

    if not path.exists():
        return {}, {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        mapa_items = data.get("mapa_item_code_a_bu", {})
        mapa_subinv = data.get("mapa_subinventory_a_bu", {})
        # Normalizar keys: UPPER + STRIP
        mapa_items = {
            str(k).strip().upper(): str(v).strip().upper()
            for k, v in mapa_items.items()
        }
        mapa_subinv = {
            str(k).strip().upper(): str(v).strip().upper()
            for k, v in mapa_subinv.items()
        }
        return mapa_items, mapa_subinv
    except Exception:
        return {}, {}


# ════════════════════════════════════════════════════════════
# NIVEL 3: REGEX DE BU EN TEXTO
# ════════════════════════════════════════════════════════════
def extraer_bus_de_texto(
    texto: str,
    patron: str = r"M\d{2}",
) -> List[str]:
    """
    Extrae todos los BUs (M01, M19, M45, etc.) de un texto.

    Ej: 'FG-R-2189LE26.M46/M45' → ['M46', 'M45']
    """
    if texto is None or pd.isna(texto):
        return []
    s = str(texto).strip().upper()
    if not s:
        return []
    return re.findall(patron, s)


# ════════════════════════════════════════════════════════════
# FUNCIÓN PRINCIPAL: INFERIR BU
# ════════════════════════════════════════════════════════════
def inferir_bu(
    df: pd.DataFrame,
    operacion: str,                          # 'sea' | 'land' | 'outbound'
    columna_item: str = "Item",
    columna_subinv: str = "Subinventory",
    columna_referencia: str = "Reference",   # se usa SEA/LAND
    columna_waybill: str = "Waybill",        # se usa OUTBOUND
    columna_descripcion: str = "Description",
    columna_bu_destino: str = "BU_Final",
    sobrescribir: bool = False,
) -> Tuple[pd.DataFrame, ReporteInferencia]:
    """
    Aplica la cascada de 4 niveles para inferir BU.

    Returns:
        (df_modificado, reporte)
    """
    config = get_config()
    op = operacion.lower()

    # Cargar mapas del maestro
    mapa_items, mapa_subinv = cargar_maestro_bu()

    # Config de regex y reglas especiales
    patron_regex = config.get("outbound_bu.patron_regex", r"M\d{2}")
    usar_ultimo = config.get("outbound_bu.usar_ultimo_si_multiple", True)
    bu_destino_misc = config.get("miscelaneus.bu_destino", "Miscelaneus")
    marcadores_ambiguos = set(
        m.upper() for m in config.get("bus_especiales.marcadores_problema", [])
    )

    # Determinar qué columna usar para regex según operación
    if op == "outbound":
        col_texto_regex = columna_waybill
    else:
        col_texto_regex = columna_referencia

    df = df.copy()
    reporte = ReporteInferencia(total_items=len(df))

    # Crear/limpiar columna destino
    if columna_bu_destino not in df.columns:
        df[columna_bu_destino] = None

    if sobrescribir:
        df[columna_bu_destino] = None

    # ────────────────────────────────────────────────────
    # PROCESAR FILA POR FILA (cascada)
    # ────────────────────────────────────────────────────
    for idx in df.index:
        # Si ya tiene BU y no estamos sobrescribiendo, saltar
        bu_actual = df.at[idx, columna_bu_destino]
        if bu_actual is not None and not pd.isna(bu_actual) \
                and str(bu_actual).strip() not in ("", "nan", "None"):
            continue

        bu_asignado = None

        # ════════════════════════════════════════════
        # NIVEL 1: Item Code → BU
        # ════════════════════════════════════════════
        if columna_item in df.columns and mapa_items:
            item = df.at[idx, columna_item]
            if item is not None and not pd.isna(item):
                item_norm = str(item).strip().upper()
                if item_norm in mapa_items:
                    bu_candidato = mapa_items[item_norm]
                    if bu_candidato not in marcadores_ambiguos:
                        bu_asignado = bu_candidato
                        reporte.nivel_1_item_code += 1

        # ════════════════════════════════════════════
        # NIVEL 2: Subinventory → BU
        # ════════════════════════════════════════════
        if bu_asignado is None and columna_subinv in df.columns and mapa_subinv:
            subinv = df.at[idx, columna_subinv]
            if subinv is not None and not pd.isna(subinv):
                subinv_norm = str(subinv).strip().upper()
                if subinv_norm in mapa_subinv:
                    bu_candidato = mapa_subinv[subinv_norm]
                    if bu_candidato in marcadores_ambiguos:
                        # AMBIGUO → bajar a nivel 3
                        reporte.ambiguos_resueltos += 1
                    else:
                        bu_asignado = bu_candidato
                        reporte.nivel_2_subinventory += 1

        # ════════════════════════════════════════════
        # NIVEL 3: Regex sobre Waybill/Reference
        # ════════════════════════════════════════════
        if bu_asignado is None and col_texto_regex in df.columns:
            texto = df.at[idx, col_texto_regex]
            bus_encontrados = extraer_bus_de_texto(texto, patron_regex)
            if bus_encontrados:
                # Reglas especiales por operación
                if op == "outbound" and usar_ultimo:
                    bu_asignado = bus_encontrados[-1]   # Último BU
                else:
                    bu_asignado = bus_encontrados[0]    # Primer BU
                reporte.nivel_3_regex += 1

        # ════════════════════════════════════════════
        # NIVEL 4: Miscelaneus o SIN_BU
        # ════════════════════════════════════════════
        if bu_asignado is None:
            # Probar regla Miscelaneus con Description o Item
            valor_eval = None
            if columna_descripcion in df.columns:
                val = df.at[idx, columna_descripcion]
                if val is not None and not pd.isna(val):
                    valor_eval = val
            if valor_eval is None and columna_item in df.columns:
                valor_eval = df.at[idx, columna_item]

            if valor_eval is not None and not pd.isna(valor_eval):
                es_misc, _ = es_miscelaneus(valor_eval)
                if es_misc:
                    bu_asignado = bu_destino_misc
                    reporte.nivel_4_miscelaneus += 1

            if bu_asignado is None:
                bu_asignado = "SIN_BU"
                reporte.nivel_4_sin_bu += 1
                # Guardar el item para reporte
                if columna_item in df.columns:
                    item_val = df.at[idx, columna_item]
                    if item_val and not pd.isna(item_val):
                        reporte.items_sin_bu.append(str(item_val).strip())

        df.at[idx, columna_bu_destino] = bu_asignado

    # ────────────────────────────────────────────────────
    # ⭐ REGLA MISCELANEUS GLOBAL (override final)
    # Aún si tiene BU, si Description match → Miscelaneus
    # ────────────────────────────────────────────────────
    if columna_descripcion in df.columns:
        for idx in df.index:
            desc = df.at[idx, columna_descripcion]
            if desc is None or pd.isna(desc):
                continue
            bu_actual = str(df.at[idx, columna_bu_destino]).strip()
            if bu_actual == bu_destino_misc:
                continue  # Ya está marcado
            es_misc, _ = es_miscelaneus(desc)
            if es_misc:
                df.at[idx, columna_bu_destino] = bu_destino_misc
                # Reasignar contadores (quitar del nivel original)
                # Nota: simplificación — no rastreamos de qué nivel vino

    # ────────────────────────────────────────────────────
    # CALCULAR DISTRIBUCIÓN FINAL
    # ────────────────────────────────────────────────────
    bus_finales = df[columna_bu_destino].value_counts().to_dict()
    reporte.bus_finales = {str(k): int(v) for k, v in bus_finales.items()}

    # Deduplicar items_sin_bu
    reporte.items_sin_bu = sorted(set(reporte.items_sin_bu))

    return df, reporte