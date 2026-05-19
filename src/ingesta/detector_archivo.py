"""
═══════════════════════════════════════════════════════════════
DETECTOR DE ARCHIVO — v2 con sistema de aliases canónicos
═══════════════════════════════════════════════════════════════
Ahora usa calcular_score_hoja() de mapeo_columnas, que entiende
TODOS los aliases (ES/EN/abreviado) en vez de keywords planas.
═══════════════════════════════════════════════════════════════
"""
import pandas as pd
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field

from src.utils.config_loader import get_config
from src.ingesta.mapeo_columnas import calcular_score_hoja, obtener_columnas_canonicas


@dataclass
class ResultadoDeteccion:
    tipo: str                                        # 'sea' | 'land' | 'outbound' | 'desconocido'
    confianza: float                                 # 0.0 - 1.0
    hoja_elegida: Optional[str] = None
    fila_header: Optional[int] = None
    scores: Dict[str, float] = field(default_factory=dict)
    razon: str = ""
    advertencias: List[str] = field(default_factory=list)
    columnas_detectadas: Dict[str, str] = field(default_factory=dict)


# ════════════════════════════════════════════════════════════
# DETECCIÓN DE FILA DE HEADER (más permisivo)
# ════════════════════════════════════════════════════════════
def detectar_fila_header(
    df_crudo: pd.DataFrame,
    max_filas: int = 15,
    min_no_vacias: int = 3,    # 🔧 antes 4 — ahora 3 para tolerar archivos chicos
) -> Optional[int]:
    """
    Recorre las primeras N filas y devuelve la fila que parece header.
    Heurística: primera fila con >=min_no_vacias celdas TEXTO no vacías.
    """
    mejor_fila = None
    mejor_score = 0

    for idx in range(min(max_filas, len(df_crudo))):
        fila = df_crudo.iloc[idx]
        no_vacias = sum(
            1 for v in fila
            if v is not None
            and not pd.isna(v)
            and isinstance(v, str)
            and v.strip() != ""
            and v.strip() not in ("X", "x", "~")   # excluir marcadores típicos
        )
        # Buscamos la fila con MÁS textos no vacíos (más probable header)
        if no_vacias >= min_no_vacias and no_vacias > mejor_score:
            mejor_score = no_vacias
            mejor_fila = idx

    return mejor_fila


# ════════════════════════════════════════════════════════════
# FUNCIÓN PRINCIPAL — usa aliases canónicos
# ════════════════════════════════════════════════════════════
def detectar_tipo_archivo(ruta_archivo: str) -> ResultadoDeteccion:
    """
    Analiza un Excel y determina si es SEA, LAND u OUTBOUND
    usando el sistema completo de aliases canónicos.
    """
    config = get_config()
    hojas_ignoradas_lower = {
        str(h).lower().strip()
        for h in config.get("hojas_ignoradas", [])
    }

    if not Path(ruta_archivo).exists():
        return ResultadoDeteccion(
            tipo="desconocido",
            confianza=0.0,
            razon=f"Archivo no existe: {ruta_archivo}",
        )

    try:
        excel = pd.ExcelFile(ruta_archivo)
    except Exception as e:
        return ResultadoDeteccion(
            tipo="desconocido",
            confianza=0.0,
            razon=f"Error abriendo archivo: {e}",
        )

    mejores_resultados: List[ResultadoDeteccion] = []

    for hoja in excel.sheet_names:
        # Filtro de hojas ignoradas (case-insensitive, substring)
        hoja_lower = hoja.lower().strip()
        if any(ign in hoja_lower for ign in hojas_ignoradas_lower):
            continue

        # Lee crudo y detecta fila header
        df_crudo = pd.read_excel(excel, sheet_name=hoja, header=None, nrows=15)
        fila_header = detectar_fila_header(df_crudo)
        if fila_header is None:
            continue

        # Re-lee con el header correcto
        try:
            df = pd.read_excel(excel, sheet_name=hoja, header=fila_header)
            df.columns = [str(c).strip() for c in df.columns]
        except Exception:
            continue

        # Score por cada tipo usando el sistema de aliases
        scores: Dict[str, float] = {}
        detalle_scores: Dict[str, Dict] = {}

        for tipo in ("outbound", "sea", "land"):
            score_info = calcular_score_hoja(df, tipo)
            scores[tipo] = score_info["score"]
            detalle_scores[tipo] = score_info

        # Elige el tipo ganador
        tipo_ganador = max(scores, key=scores.get)
        score_ganador = scores[tipo_ganador]
        info_ganador = detalle_scores[tipo_ganador]

        # Validar que TENGA las columnas críticas (no solo score alto)
        if info_ganador["faltantes"]:
            continue

        # Score mínimo del config (con default razonable)
        umbral = config.get(f"deteccion.{tipo_ganador}.score_minimo", 15)

        if score_ganador >= umbral:
            confianza = min(score_ganador / 50, 1.0)
            mejores_resultados.append(
                ResultadoDeteccion(
                    tipo=tipo_ganador,
                    confianza=confianza,
                    hoja_elegida=hoja,
                    fila_header=fila_header,
                    scores=scores,
                    razon=f"Score {score_ganador} ≥ umbral {umbral} en hoja '{hoja}'",
                    columnas_detectadas=obtener_columnas_canonicas(df),
                )
            )

    if not mejores_resultados:
        return ResultadoDeteccion(
            tipo="desconocido",
            confianza=0.0,
            razon="Ninguna hoja superó el umbral mínimo de score",
        )

    # Devuelve el de mayor confianza
    mejor = max(mejores_resultados, key=lambda r: r.confianza)
    return mejor