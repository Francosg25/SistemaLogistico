"""
Generador del Summary consolidado (Bloque 6).

Toma los resultados de Outbound, Sea y Land y genera:
- Tabla pivote de %PCT por BU
- Tabla de montos por BU
- Tabla consolidada completa

🔧 FIX: Maneja correctamente el nombre de columna %PCT en cada operación:
    - Sea usa '%PCT (Summary)' (que excluye Capex/MCS)
    - Land usa '%PCT'
    - Outbound usa '%PCT'
"""
import pandas as pd
import numpy as np
from typing import List, Dict, Optional
from dataclasses import dataclass, field

from src.utils.logger import configurar_logger

logger = configurar_logger("generar_summary")


@dataclass
class ResultadoSummary:
    tabla_pct: pd.DataFrame
    tabla_montos: pd.DataFrame
    tabla_consolidada: pd.DataFrame
    bus_orden: List[str]
    metricas: Dict[str, any] = field(default_factory=dict)
    advertencias: List[str] = field(default_factory=list)


# ============================================================
# FUNCIONES AUXILIARES
# ============================================================
def _obtener_columna_pct(df: pd.DataFrame, nombres_posibles: List[str]) -> Optional[str]:
    """
    🔧 Detecta cuál columna de %PCT usar en un DataFrame.
    Devuelve el primer nombre que encuentre.
    """
    for nombre in nombres_posibles:
        if nombre in df.columns:
            return nombre
    return None


def _obtener_columna_monto(df: pd.DataFrame, nombres_posibles: List[str]) -> Optional[str]:
    """Detecta cuál columna de monto USD usar."""
    for nombre in nombres_posibles:
        if nombre in df.columns:
            return nombre
    return None


def _ordenar_bus(bus: List[str]) -> List[str]:
    """
    Ordena los BUs así:
    1. BUs estándar Mxx (M01, M19, M23, ...) en orden numérico
    2. BUs especiales al final (Capex, MCS, Machine, Miscelaneus)
    """
    estandar = []
    especiales = []
    
    for bu in bus:
        if bu is None or not isinstance(bu, str):
            continue
        bu_strip = bu.strip()
        if not bu_strip:
            continue
        
        # Es estándar si empieza con M y le siguen dígitos
        if (bu_strip.startswith("M") and 
            len(bu_strip) > 1 and 
            bu_strip[1:].isdigit()):
            estandar.append(bu_strip)
        else:
            especiales.append(bu_strip)
    
    # Ordenar estándar por número
    estandar.sort(key=lambda x: int(x[1:]))
    
    # Ordenar especiales: Capex y MCS primero, luego alfabético
    orden_especiales = {"Capex": 0, "MCS": 1, "Machine": 2, "Miscelaneus": 3}
    especiales.sort(key=lambda x: (orden_especiales.get(x, 99), x))
    
    return estandar + especiales


# ============================================================
# FUNCIÓN PRINCIPAL
# ============================================================
def generar_summary(
    resultado_outbound,
    resultado_sea,
    resultado_land,
) -> ResultadoSummary:
    """
    Genera el Summary consolidado a partir de los 3 procesadores.
    
    Args:
        resultado_outbound: ResultadoOutbound del Bloque 3
        resultado_sea: ResultadoSea del Bloque 4
        resultado_land: ResultadoLand del Bloque 5
    
    Returns:
        ResultadoSummary con tablas pivote
    """
    logger.info("=" * 60)
    logger.info("📊 INICIANDO GENERACIÓN DEL SUMMARY")
    logger.info("=" * 60)
    
    advertencias = []
    
    # ─────────────────────────────────────────────────────────
    # 1. EXTRAER LOS DataFrames DE RESUMEN POR BU
    # ─────────────────────────────────────────────────────────
    df_out = resultado_outbound.resumen_bu.copy()
    df_sea = resultado_sea.resumen_bu.copy()
    df_land = resultado_land.resumen_bu.copy()
    
    logger.info(f"📋 Outbound:  {len(df_out)} BUs → columnas: {list(df_out.columns)}")
    logger.info(f"📋 Sea:       {len(df_sea)} BUs → columnas: {list(df_sea.columns)}")
    logger.info(f"📋 Land:      {len(df_land)} BUs → columnas: {list(df_land.columns)}")
    
    # ─────────────────────────────────────────────────────────
    # 2. 🔧 DETECTAR LAS COLUMNAS %PCT Y MONTO CORRECTAS
    # ─────────────────────────────────────────────────────────
    # Sea: PRIORIZAR '%PCT (Summary)' (que ya excluye Capex y MCS)
    col_pct_sea = _obtener_columna_pct(df_sea, ["%PCT (Summary)", "%PCT", "%PCT (Total)"])
    col_pct_land = _obtener_columna_pct(df_land, ["%PCT", "%PCT (Summary)"])
    col_pct_out = _obtener_columna_pct(df_out, ["%PCT", "%PCT (Summary)"])
    
    col_monto_sea = _obtener_columna_monto(df_sea, ["Amount (USD)", "Cost", "Monto Total (USD)"])
    col_monto_land = _obtener_columna_monto(df_land, ["Monto Total (USD)", "Amount (USD)", "Cost"])
    col_monto_out = _obtener_columna_monto(df_out, ["Log. Exp (USD)", "Monto Total (USD)", "Amount (USD)"])
    
    logger.info(f"🔍 Columnas %PCT detectadas:")
    logger.info(f"   Sea:      '{col_pct_sea}'")
    logger.info(f"   Land:     '{col_pct_land}'")
    logger.info(f"   Outbound: '{col_pct_out}'")
    logger.info(f"🔍 Columnas Monto detectadas:")
    logger.info(f"   Sea:      '{col_monto_sea}'")
    logger.info(f"   Land:     '{col_monto_land}'")
    logger.info(f"   Outbound: '{col_monto_out}'")
    
    # Validar
    if not all([col_pct_sea, col_pct_land, col_pct_out]):
        raise ValueError(
            f"No se encontraron las columnas %PCT esperadas. "
            f"Sea: {col_pct_sea}, Land: {col_pct_land}, Outbound: {col_pct_out}"
        )
    
    if not all([col_monto_sea, col_monto_land, col_monto_out]):
        raise ValueError(
            f"No se encontraron las columnas de monto esperadas. "
            f"Sea: {col_monto_sea}, Land: {col_monto_land}, Outbound: {col_monto_out}"
        )
    
    # ─────────────────────────────────────────────────────────
    # 3. UNIFICAR LISTA DE BUs
    # ─────────────────────────────────────────────────────────
    bus_sea = set(df_sea["BU"].dropna().astype(str).str.strip().unique())
    bus_land = set(df_land["BU"].dropna().astype(str).str.strip().unique())
    bus_out = set(df_out["BU"].dropna().astype(str).str.strip().unique())
    
    todos_los_bus = bus_sea | bus_land | bus_out
    bus_orden = _ordenar_bus(list(todos_los_bus))
    
    logger.info(f"🏷️  BUs únicos detectados ({len(bus_orden)}): {bus_orden}")
    
    # ─────────────────────────────────────────────────────────
    # 4. CONSTRUIR LA TABLA DE %PCT (excluyendo Capex y MCS)
    # ─────────────────────────────────────────────────────────
    bus_pct = [bu for bu in bus_orden if bu not in ("Capex", "MCS")]
    
    def _obtener_pct(df: pd.DataFrame, bu: str, col_pct: str) -> float:
        """Devuelve el %PCT del BU dado, o 0 si no existe."""
        if df is None or len(df) == 0:
            return 0.0
        fila = df[df["BU"].astype(str).str.strip() == bu]
        if len(fila) == 0:
            return 0.0
        valor = fila[col_pct].iloc[0]
        if pd.isna(valor):
            return 0.0
        return float(valor)
    
    fila_sea_pct = {"Type": "Sea %PCT"}
    fila_land_pct = {"Type": "Land %PCT"}
    fila_out_pct = {"Type": "Outbound %PCT"}
    
    for bu in bus_pct:
        fila_sea_pct[bu] = _obtener_pct(df_sea, bu, col_pct_sea)
        fila_land_pct[bu] = _obtener_pct(df_land, bu, col_pct_land)
        fila_out_pct[bu] = _obtener_pct(df_out, bu, col_pct_out)
    
    tabla_pct = pd.DataFrame([fila_sea_pct, fila_land_pct, fila_out_pct])
    
    # ─────────────────────────────────────────────────────────
    # 5. CONSTRUIR LA TABLA DE MONTOS (incluye TODOS los BUs)
    # ─────────────────────────────────────────────────────────
    def _obtener_monto(df: pd.DataFrame, bu: str, col_monto: str) -> float:
        """Devuelve el monto USD del BU dado, o 0 si no existe."""
        if df is None or len(df) == 0:
            return 0.0
        fila = df[df["BU"].astype(str).str.strip() == bu]
        if len(fila) == 0:
            return 0.0
        valor = fila[col_monto].iloc[0]
        if pd.isna(valor):
            return 0.0
        return float(valor)
    
    total_sea = df_sea[col_monto_sea].sum()
    total_land = df_land[col_monto_land].sum()
    total_out = df_out[col_monto_out].sum()
    
    fila_sea_monto = {"Viewer": "Sea", "Arg. Var $": total_sea}
    fila_land_monto = {"Viewer": "Land", "Arg. Var $": total_land}
    fila_out_monto = {"Viewer": "Outbound", "Arg. Var $": total_out}
    
    for bu in bus_orden:
        fila_sea_monto[bu] = _obtener_monto(df_sea, bu, col_monto_sea)
        fila_land_monto[bu] = _obtener_monto(df_land, bu, col_monto_land)
        fila_out_monto[bu] = _obtener_monto(df_out, bu, col_monto_out)
    
    tabla_montos = pd.DataFrame([fila_sea_monto, fila_land_monto, fila_out_monto])
    
    # ─────────────────────────────────────────────────────────
    # 6. CONSTRUIR LA TABLA CONSOLIDADA
    # ─────────────────────────────────────────────────────────
    filas_consolidadas = []
    for bu in bus_orden:
        monto_sea = _obtener_monto(df_sea, bu, col_monto_sea)
        monto_land = _obtener_monto(df_land, bu, col_monto_land)
        monto_out = _obtener_monto(df_out, bu, col_monto_out)
        total_bu = monto_sea + monto_land + monto_out
        
        pct_sea = _obtener_pct(df_sea, bu, col_pct_sea) if bu in bus_pct else 0.0
        pct_land = _obtener_pct(df_land, bu, col_pct_land) if bu in bus_pct else 0.0
        pct_out = _obtener_pct(df_out, bu, col_pct_out) if bu in bus_pct else 0.0
        
        filas_consolidadas.append({
            "BU": bu,
            "Sea %PCT": pct_sea,
            "Land %PCT": pct_land,
            "Outbound %PCT": pct_out,
            "Monto Sea": monto_sea,
            "Monto Land": monto_land,
            "Monto Outbound": monto_out,
            "TOTAL BU": total_bu,
            "Es Especial": bu in ("Capex", "MCS", "Machine", "Miscelaneus"),
        })
    
    tabla_consolidada = pd.DataFrame(filas_consolidadas)
    
    # ─────────────────────────────────────────────────────────
    # 7. MÉTRICAS GENERALES
    # ─────────────────────────────────────────────────────────
    gran_total = total_sea + total_land + total_out
    
    # Suma de %PCT (para validación: cada fila debería sumar 100%)
    suma_pct_sea = sum(fila_sea_pct[bu] for bu in bus_pct)
    suma_pct_land = sum(fila_land_pct[bu] for bu in bus_pct)
    suma_pct_out = sum(fila_out_pct[bu] for bu in bus_pct)
    
    bus_no_estandar = [bu for bu in bus_orden if not (bu.startswith("M") and bu[1:].isdigit())]
    
    metricas = {
        "total_sea_usd": round(total_sea, 2),
        "total_land_usd": round(total_land, 2),
        "total_outbound_usd": round(total_out, 2),
        "gran_total_usd": round(gran_total, 2),
        "total_bus": len(bus_orden),
        "bus_orden": bus_orden,
        "bus_nuevos": bus_no_estandar,
        "suma_pct_sea": round(suma_pct_sea, 4),
        "suma_pct_land": round(suma_pct_land, 4),
        "suma_pct_outbound": round(suma_pct_out, 4),
    }
    
    # ─────────────────────────────────────────────────────────
    # 8. LOG FINAL
    # ─────────────────────────────────────────────────────────
    logger.info("─" * 60)
    logger.info(f"💰 Total Sea:      ${total_sea:,.2f}")
    logger.info(f"💰 Total Land:     ${total_land:,.2f}")
    logger.info(f"💰 Total Outbound: ${total_out:,.2f}")
    logger.info(f"💰 GRAN TOTAL:     ${gran_total:,.2f}")
    logger.info(f"📊 Suma %PCT Sea:      {suma_pct_sea:.2%}")
    logger.info(f"📊 Suma %PCT Land:     {suma_pct_land:.2%}")
    logger.info(f"📊 Suma %PCT Outbound: {suma_pct_out:.2%}")
    logger.info("=" * 60)
    
    return ResultadoSummary(
        tabla_pct=tabla_pct,
        tabla_montos=tabla_montos,
        tabla_consolidada=tabla_consolidada,
        bus_orden=bus_orden,
        metricas=metricas,
        advertencias=advertencias,
    )