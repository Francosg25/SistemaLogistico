"""
═══════════════════════════════════════════════════════════════
DETECTOR AUTOMÁTICO DE FILA DE ENCABEZADO
═══════════════════════════════════════════════════════════════
Las hojas pueden tener el encabezado en fila 1, 3, 5, 8, etc.
Este módulo detecta automáticamente cuál fila es el encabezado
buscando la que tiene más nombres reconocibles como columnas.

🔧 v2 — Mejoras:
  • Escaneo hasta fila 20 (no 15)
  • Bonus por cobertura horizontal (favorece headers dispersos)
  • Bonus por columnas CRÍTICAS presentes
  • Filtrado de filas "ruido" (numeración, merged cells)
  • Logging detallado para diagnóstico
═══════════════════════════════════════════════════════════════
"""
import pandas as pd
import re
from typing import Optional, Tuple, List

from src.ingesta.mapeo_columnas import buscar_columna_logica
from src.utils.logger import configurar_logger

logger = configurar_logger("detector_header")


# ════════════════════════════════════════════════════════════
# COLUMNAS CRÍTICAS QUE DAN BONUS
# ════════════════════════════════════════════════════════════
# Si la fila contiene alguna de estas, sube su score significativamente
COLUMNAS_CRITICAS_BONUS = {
    "Reference",
    "BU",
    "Peso Bruto",
    "Item",
    "Container",
}


# ════════════════════════════════════════════════════════════
# PATRONES DE FILAS "RUIDO" QUE NO SON HEADERS
# ════════════════════════════════════════════════════════════
# Filas de numeración (1, 2, 3...) o de merged cells
PATRON_NUMERICO_SECUENCIAL = re.compile(r"^\d{1,3}$")  # "1", "2", "10", "75"
PATRON_MERGED = re.compile(r"\[MERGED.*\]|~")


def _es_fila_ruido(valores: List[str]) -> bool:
    """
    Detecta si una fila es "ruido" (numeración, merged cells, etc.)
    y NO es un header válido.
    
    Ejemplos de filas ruido:
      - "1", "2", "3", "4", ... (numeración de columnas)
      - "x", "x", "x", ... (marcadores de columna)
      - "Data", "" , "" , "" (titulos de sección con merged)
    """
    no_vacias = [v for v in valores if v]
    if not no_vacias:
        return True
    
    # ¿Más del 60% son números secuenciales tipo "1", "2", "3"?
    numericos = sum(1 for v in no_vacias if PATRON_NUMERICO_SECUENCIAL.match(v))
    if numericos / len(no_vacias) > 0.6:
        return True
    
    # ¿Más del 60% son marcadores "x" o "X"?
    equis = sum(1 for v in no_vacias if v.lower() in ("x", "xx"))
    if equis / len(no_vacias) > 0.6:
        return True
    
    # ¿Más del 40% tienen patrón MERGED?
    merged = sum(1 for v in no_vacias if PATRON_MERGED.search(v))
    if merged / len(no_vacias) > 0.4:
        return True
    
    return False


def _calcular_cobertura_horizontal(posiciones_reconocidas: List[int]) -> float:
    """
    Calcula qué tan dispersos están los headers a lo largo de la fila.
    
    Devuelve un valor entre 0 y 1:
      - 0   = todos los headers están agrupados juntos
      - 1   = los headers están bien dispersos por toda la fila
    
    Esto ayuda a distinguir:
      - Fila 4 con headers solo en cols 60-67 (cobertura baja) ❌
      - Fila 8 con headers en cols 4, 12, 55, 61 (cobertura alta) ✅
    """
    if len(posiciones_reconocidas) < 2:
        return 0.0
    
    rango = max(posiciones_reconocidas) - min(posiciones_reconocidas)
    return min(rango / 50.0, 1.0)  # Normalizado a max 50 columnas


def detectar_fila_encabezado(
    archivo,
    nombre_hoja: str,
    max_filas_escanear: int = 20,         # 🔧 Era 15, ahora 20
    min_columnas_reconocidas: int = 3,
) -> Tuple[Optional[int], int]:
    """
    Escanea las primeras N filas de una hoja y devuelve la fila más probable
    de ser el encabezado.
    
    Algoritmo de scoring:
      • +10 por cada columna reconocida
      • +5 bonus por cada columna CRÍTICA (Reference, BU, Peso Bruto, Item, Container)
      • +0 a +15 por dispersión horizontal (cobertura de la fila)
      • -100 si la fila es "ruido" (numeración, merged)
    
    Args:
        archivo: Path o file-like del Excel
        nombre_hoja: Nombre de la hoja a analizar
        max_filas_escanear: Cuántas filas escanear desde arriba (default 20)
        min_columnas_reconocidas: Mínimo de columnas válidas (default 3)
    
    Returns:
        Tupla:
          - fila_header (0-indexed): índice de la fila de encabezado, o None
          - num_columnas_reconocidas: cuántas columnas válidas tiene
    """
    try:
        if hasattr(archivo, "seek"):
            archivo.seek(0)
        
        # Leer sin encabezado (para escanear manualmente)
        df_raw = pd.read_excel(
            archivo,
            sheet_name=nombre_hoja,
            header=None,
            nrows=max_filas_escanear,
            dtype=object,
        )
    except Exception as e:
        logger.warning(f"   No se pudo leer hoja '{nombre_hoja}': {e}")
        return None, 0
    
    # ─────────────────────────────────────────────────────
    # ESCANEAR cada fila y calcular su score
    # ─────────────────────────────────────────────────────
    candidatas = []  # Lista de (idx, score, num_reconocidas, motivo)
    
    for idx, fila in df_raw.iterrows():
        valores = [str(v).strip() if pd.notna(v) else "" for v in fila.values]
        
        # ─── Filtro 1: Filas vacías ───
        no_vacias = sum(1 for v in valores if v)
        if no_vacias < min_columnas_reconocidas:
            continue
        
        # ─── Filtro 2: Filas "ruido" (numeración, merged) ───
        if _es_fila_ruido(valores):
            logger.debug(f"   Fila {idx+1}: descartada (ruido)")
            continue
        
        # ─── Contar columnas reconocidas y críticas ───
        posiciones_reconocidas = []
        columnas_criticas_encontradas = set()
        
        for pos, valor in enumerate(valores):
            if not valor:
                continue
            
            col_logica = buscar_columna_logica(valor)
            if col_logica is not None:
                posiciones_reconocidas.append(pos)
                if col_logica in COLUMNAS_CRITICAS_BONUS:
                    columnas_criticas_encontradas.add(col_logica)
        
        reconocidas = len(posiciones_reconocidas)
        
        # ─── Filtro 3: Mínimo de columnas reconocidas ───
        if reconocidas < min_columnas_reconocidas:
            continue
        
        # ─── Cálculo del score ───
        score_base = reconocidas * 10
        bonus_criticas = len(columnas_criticas_encontradas) * 5
        cobertura = _calcular_cobertura_horizontal(posiciones_reconocidas)
        bonus_cobertura = int(cobertura * 15)
        
        score_total = score_base + bonus_criticas + bonus_cobertura
        
        candidatas.append({
            "fila": idx,
            "score": score_total,
            "reconocidas": reconocidas,
            "criticas": sorted(columnas_criticas_encontradas),
            "cobertura_pct": round(cobertura * 100, 1),
        })
        
        logger.debug(
            f"   Fila {idx+1}: {reconocidas} cols reconocidas, "
            f"{len(columnas_criticas_encontradas)} críticas "
            f"({sorted(columnas_criticas_encontradas)}), "
            f"cobertura {round(cobertura*100,1)}%, score={score_total}"
        )
    
    # ─────────────────────────────────────────────────────
    # ELEGIR LA MEJOR CANDIDATA
    # ─────────────────────────────────────────────────────
    if not candidatas:
        logger.info(f"   ❌ No se encontró fila de encabezado válida")
        return None, 0
    
    # Ordenar por score descendente
    candidatas.sort(key=lambda x: -x["score"])
    mejor = candidatas[0]
    
    # ─── Log de candidatas (top 3 para diagnóstico) ───
    if len(candidatas) > 1:
        logger.info(f"   📊 Candidatas encontradas: {len(candidatas)}")
        for i, c in enumerate(candidatas[:3]):
            marca = "🏆" if i == 0 else "  "
            logger.info(
                f"   {marca} Fila {c['fila']+1}: score={c['score']} | "
                f"{c['reconocidas']} cols | críticas: {c['criticas']} | "
                f"cobertura: {c['cobertura_pct']}%"
            )
    
    logger.info(
        f"   📐 Fila de encabezado detectada: fila {mejor['fila'] + 1} "
        f"(score: {mejor['score']}, {mejor['reconocidas']} columnas, "
        f"críticas: {mejor['criticas']})"
    )
    
    return mejor["fila"], mejor["reconocidas"]