"""
Motor central de reglas dinámicas del sistema.

RESPONSABILIDADES:
═══════════════════════════════════════════════════════════════
1. Detectar TODOS los BUs presentes en los datos del mes actual
2. Comparar contra el catálogo histórico
3. Identificar:
   - BUs NUEVOS (no vistos antes)
   - BUs RECURRENTES (vistos en meses anteriores)
   - BUs DESAPARECIDOS (existían pero ya no aparecen)
4. Generar alertas para que el usuario valide los nuevos
5. Aplicar las reglas especiales conocidas (Capex/MCS exclusión, etc.)
═══════════════════════════════════════════════════════════════

REGLA CRÍTICA (de REGLAS_PROCESO líneas 7-23):
    🔴 NO ENCASILLARSE CON LOS MISMOS BU
    ✅ SIEMPRE leer los BU directamente de los datos fuente
    ❌ NUNCA asumir que serán iguales al mes anterior
"""
import pandas as pd
from typing import Dict, List, Set, Optional
from dataclasses import dataclass, field
from datetime import datetime

from src.reglas.catalogo_manager import obtener_catalogo, CatalogoManager
from src.reglas.inferencia_bu import inferir_bu_desde_reference
from src.utils.logger import configurar_logger

logger = configurar_logger("motor_reglas")


# ============================================================
# ESTRUCTURA DE RESULTADO
# ============================================================
@dataclass
class ResultadoComparacionBU:
    """Resultado de comparar BUs actuales contra el catálogo histórico."""
    bus_actuales: Set[str] = field(default_factory=set)
    bus_nuevos: Set[str] = field(default_factory=set)         # En datos, NO en catálogo
    bus_recurrentes: Set[str] = field(default_factory=set)    # En datos Y en catálogo
    bus_desaparecidos: Set[str] = field(default_factory=set)  # En catálogo, NO en datos
    bus_por_operacion: Dict[str, Set[str]] = field(default_factory=dict)
    alertas: List[Dict] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        """Convierte a dict para JSON/Streamlit."""
        return {
            "bus_actuales": sorted(self.bus_actuales),
            "bus_nuevos": sorted(self.bus_nuevos),
            "bus_recurrentes": sorted(self.bus_recurrentes),
            "bus_desaparecidos": sorted(self.bus_desaparecidos),
            "bus_por_operacion": {
                op: sorted(bus) for op, bus in self.bus_por_operacion.items()
            },
            "alertas": self.alertas,
            "requiere_validacion": len(self.bus_nuevos) > 0,
        }


# ============================================================
# FUNCIÓN 1: DETECTAR BUs ACTUALES
# ============================================================
def detectar_bus_actuales(
    df_sea: Optional[pd.DataFrame] = None,
    df_land: Optional[pd.DataFrame] = None,
    df_outbound: Optional[pd.DataFrame] = None,
    columna_bu: str = "BU",
    columna_reference_outbound: str = "Reference",
) -> Dict[str, Set[str]]:
    """
    Extrae TODOS los BUs presentes en los DataFrames de las 3 operaciones.
    
    Para Outbound aplica inferencia desde el Reference (Bloque 3).
    Para Sea y Land lee directamente la columna BU.
    
    Args:
        df_sea: DataFrame de SEA (output del Bloque 2)
        df_land: DataFrame de LAND
        df_outbound: DataFrame de OUTBOUND
        columna_bu: Nombre de la columna BU
        columna_reference_outbound: Nombre de la columna Reference en Outbound
    
    Returns:
        Diccionario {'sea': {'M01', 'M19'...}, 'land': {...}, 'outbound': {...}, 'todos': {...}}
    """
    logger.info("🔍 Detectando BUs en los datos actuales...")
    
    resultado = {
        "sea": set(),
        "land": set(),
        "outbound": set(),
        "todos": set(),
    }
    
    # ── SEA: Leer directamente la columna BU
    if df_sea is not None and len(df_sea) > 0 and columna_bu in df_sea.columns:
        bus_sea = df_sea[columna_bu].dropna().astype(str).str.strip()
        bus_sea = bus_sea[bus_sea != ""]
        resultado["sea"] = set(bus_sea.unique())
        logger.info(f"   SEA:      {len(resultado['sea'])} BUs → {sorted(resultado['sea'])}")
    
    # ── LAND: Leer directamente la columna BU
    if df_land is not None and len(df_land) > 0 and columna_bu in df_land.columns:
        bus_land = df_land[columna_bu].dropna().astype(str).str.strip()
        bus_land = bus_land[bus_land != ""]
        resultado["land"] = set(bus_land.unique())
        logger.info(f"   LAND:     {len(resultado['land'])} BUs → {sorted(resultado['land'])}")
    
    # ── OUTBOUND: Inferir desde el Reference (Bloque 3)
    if df_outbound is not None and len(df_outbound) > 0:
        if columna_reference_outbound in df_outbound.columns:
            bus_inferidos = df_outbound[columna_reference_outbound].apply(
                inferir_bu_desde_reference
            )
            bus_validos = [bu for bu in bus_inferidos.dropna().unique() if bu]
            resultado["outbound"] = set(bus_validos)
            logger.info(f"   OUTBOUND: {len(resultado['outbound'])} BUs → {sorted(resultado['outbound'])}")
    
    # Unificar todos
    resultado["todos"] = resultado["sea"] | resultado["land"] | resultado["outbound"]
    logger.info(f"   TOTAL:    {len(resultado['todos'])} BUs únicos → {sorted(resultado['todos'])}")
    
    return resultado


# ============================================================
# FUNCIÓN 2: COMPARAR CONTRA CATÁLOGO HISTÓRICO
# ============================================================
def comparar_con_historico(
    bus_actuales_por_operacion: Dict[str, Set[str]],
    catalogo: Optional[CatalogoManager] = None,
) -> ResultadoComparacionBU:
    """
    Compara los BUs detectados contra el catálogo histórico.
    
    Identifica:
    - BUs NUEVOS: están en los datos pero NO en el catálogo
    - BUs RECURRENTES: están en ambos
    - BUs DESAPARECIDOS: están en el catálogo pero NO en los datos
    
    Args:
        bus_actuales_por_operacion: Output de detectar_bus_actuales()
        catalogo: Instancia del CatalogoManager (usa el singleton si es None)
    
    Returns:
        ResultadoComparacionBU con clasificación y alertas
    """
    logger.info("🔄 Comparando BUs contra catálogo histórico...")
    
    if catalogo is None:
        catalogo = obtener_catalogo()
    
    bus_actuales = bus_actuales_por_operacion.get("todos", set())
    bus_historicos = catalogo.bus_conocidos
    
    # Clasificación
    bus_nuevos = bus_actuales - bus_historicos
    bus_recurrentes = bus_actuales & bus_historicos
    bus_desaparecidos = bus_historicos - bus_actuales
    
    # Generar alertas
    alertas = []
    
    # ── Alerta 1: BUs nuevos detectados
    if bus_nuevos:
        for bu in sorted(bus_nuevos):
            # Detectar en qué operación apareció
            ops_donde_aparece = [
                op for op in ["sea", "land", "outbound"]
                if bu in bus_actuales_por_operacion.get(op, set())
            ]
            alertas.append({
                "tipo": "BU_NUEVO",
                "severidad": "WARNING",
                "bu": bu,
                "operaciones": ops_donde_aparece,
                "mensaje": (
                    f"BU '{bu}' es NUEVO (no existía en el catálogo). "
                    f"Apareció en: {', '.join(ops_donde_aparece)}. "
                    f"Valida si es correcto o si hay un typo."
                ),
                "accion_sugerida": "Validar manualmente y agregar al catálogo si es correcto.",
            })
    
    # ── Alerta 2: BUs que desaparecieron este mes
    if bus_desaparecidos:
        for bu in sorted(bus_desaparecidos):
            info = catalogo.info_bu(bu)
            ultima = info.get("ultima_aparicion", "desconocida") if info else "?"
            alertas.append({
                "tipo": "BU_DESAPARECIDO",
                "severidad": "INFO",
                "bu": bu,
                "ultima_aparicion": ultima,
                "mensaje": (
                    f"BU '{bu}' existía en el catálogo pero NO aparece este mes. "
                    f"Última aparición: {ultima[:10] if isinstance(ultima, str) else '?'}. "
                    f"Esto es normal si la BU no tuvo movimientos."
                ),
                "accion_sugerida": "Solo informativo. No requiere acción.",
            })
    
    # ── Alerta 3: BUs especiales presentes (recordatorio de reglas)
    bus_especiales_presentes = bus_actuales & catalogo.bus_especiales
    for bu in sorted(bus_especiales_presentes):
        info = catalogo.info_bu(bu) or {}
        if not info.get("incluir_en_summary_pct", True):
            alertas.append({
                "tipo": "REGLA_ESPECIAL",
                "severidad": "INFO",
                "bu": bu,
                "mensaje": (
                    f"BU '{bu}' tiene regla especial: "
                    f"{info.get('razon_exclusion', 'Excluido del %PCT del Summary')}."
                ),
                "accion_sugerida": "Se aplicará automáticamente la regla del catálogo.",
            })
    
    logger.info(f"   ✨ Nuevos:        {len(bus_nuevos)} → {sorted(bus_nuevos)}")
    logger.info(f"   ♻️  Recurrentes:  {len(bus_recurrentes)} → {sorted(bus_recurrentes)}")
    logger.info(f"   👻 Desaparecidos: {len(bus_desaparecidos)} → {sorted(bus_desaparecidos)}")
    logger.info(f"   🚨 Alertas:       {len(alertas)}")
    
    return ResultadoComparacionBU(
        bus_actuales=bus_actuales,
        bus_nuevos=bus_nuevos,
        bus_recurrentes=bus_recurrentes,
        bus_desaparecidos=bus_desaparecidos,
        bus_por_operacion={
            "sea": bus_actuales_por_operacion.get("sea", set()),
            "land": bus_actuales_por_operacion.get("land", set()),
            "outbound": bus_actuales_por_operacion.get("outbound", set()),
        },
        alertas=alertas,
    )


# ============================================================
# FUNCIÓN 3: OBTENER ALERTAS FORMATEADAS
# ============================================================
def obtener_alertas_bu(comparacion: ResultadoComparacionBU) -> Dict[str, List[str]]:
    """
    Formatea las alertas en mensajes legibles agrupados por severidad.
    Útil para mostrar en la UI de Streamlit.
    
    Returns:
        {'errores': [...], 'warnings': [...], 'info': [...]}
    """
    formato = {"errores": [], "warnings": [], "info": []}
    
    for alerta in comparacion.alertas:
        mensaje = alerta["mensaje"]
        severidad = alerta.get("severidad", "INFO")
        
        if severidad == "ERROR":
            formato["errores"].append(mensaje)
        elif severidad == "WARNING":
            formato["warnings"].append(mensaje)
        else:
            formato["info"].append(mensaje)
    
    return formato


# ============================================================
# FUNCIÓN 4: REGISTRAR BUs VALIDADOS (después de UI)
# ============================================================
def registrar_bus_validados(
    bus_a_registrar: List[Dict],
    catalogo: Optional[CatalogoManager] = None,
) -> int:
    """
    Registra en el catálogo los BUs que el usuario validó manualmente desde la UI.
    
    Args:
        bus_a_registrar: Lista de dicts con estructura:
            [
                {
                    'bu': 'M47',
                    'operacion': 'sea',
                    'descripcion': 'Nueva línea M47',
                    'es_estandar': True,
                    'incluir_en_summary_pct': True,
                },
                ...
            ]
        catalogo: Instancia (singleton por default)
    
    Returns:
        Número de BUs registrados exitosamente
    """
    if catalogo is None:
        catalogo = obtener_catalogo()
    
    registrados = 0
    for entrada in bus_a_registrar:
        try:
            catalogo.registrar_bu(
                bu=entrada["bu"],
                operacion=entrada["operacion"],
                descripcion=entrada.get("descripcion", ""),
                es_estandar=entrada.get("es_estandar", False),
                es_especial=entrada.get("es_especial", False),
                incluir_en_summary_pct=entrada.get("incluir_en_summary_pct", True),
            )
            registrados += 1
        except Exception as e:
            logger.error(f"Error registrando BU {entrada}: {e}")
    
    logger.info(f"✅ {registrados}/{len(bus_a_registrar)} BUs registrados en catálogo")
    return registrados


# ============================================================
# FUNCIÓN 5: ACTUALIZAR FECHAS DE APARICIÓN (post-proceso)
# ============================================================
def actualizar_apariciones(
    bus_por_operacion: Dict[str, Set[str]],
    catalogo: Optional[CatalogoManager] = None,
) -> None:
    """
    Actualiza la fecha de 'ultima_aparicion' para todos los BUs recurrentes.
    Se llama al final del proceso, una vez que el usuario aprobó los resultados.
    """
    if catalogo is None:
        catalogo = obtener_catalogo()
    
    for operacion, bus in bus_por_operacion.items():
        if operacion == "todos":
            continue
        for bu in bus:
            if catalogo.es_conocido(bu):
                catalogo.registrar_aparicion(bu, operacion)