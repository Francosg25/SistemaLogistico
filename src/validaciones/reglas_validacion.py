"""
Reglas individuales de validación.
Cada función valida UN aspecto específico y retorna una lista de Hallazgos.
"""
import pandas as pd
import numpy as np
from typing import List, Optional, Dict

from src.validaciones.reporte_validacion import Hallazgo, Severidad
from src.utils.logger import configurar_logger

logger = configurar_logger("reglas_validacion")


# Tolerancia para comparaciones numéricas
TOLERANCIA_COSTO = 0.01      # USD
TOLERANCIA_PCT = 0.0001      # 0.01%


# ════════════════════════════════════════════════════════════
# REGLA 1: CONSERVACIÓN DE COSTO POR OPERACIÓN
# ════════════════════════════════════════════════════════════
def validar_conservacion_costo(
    operacion: str,
    metricas: Dict,
) -> List[Hallazgo]:
    """
    Verifica que: Σ(costos asignados) ≈ #Grupos × Costo_Fijo
    
    Esta es la validación más importante. Si falla, hay un bug
    en la distribución proporcional.
    """
    hallazgos = []
    
    esperado = metricas.get("costo_total_esperado", 0)
    calculado = metricas.get("costo_total_calculado", 0)
    diferencia = abs(esperado - calculado)
    
    if diferencia < TOLERANCIA_COSTO:
        hallazgos.append(Hallazgo(
            regla="Conservación de costo",
            severidad=Severidad.OK,
            operacion=operacion,
            mensaje=(
                f"✅ Suma de costos coincide con esperado: "
                f"${calculado:,.2f} = ${esperado:,.2f}"
            ),
            valor_esperado=f"${esperado:,.2f}",
            valor_obtenido=f"${calculado:,.2f}",
        ))
    elif diferencia < 1.0:
        hallazgos.append(Hallazgo(
            regla="Conservación de costo",
            severidad=Severidad.WARNING,
            operacion=operacion,
            mensaje=(
                f"⚠️ Pequeña diferencia en suma de costos: "
                f"${diferencia:.4f} (probablemente redondeo)"
            ),
            valor_esperado=f"${esperado:,.2f}",
            valor_obtenido=f"${calculado:,.2f}",
            accion_sugerida="Revisar si el redondeo es aceptable.",
        ))
    else:
        hallazgos.append(Hallazgo(
            regla="Conservación de costo",
            severidad=Severidad.ERROR,
            operacion=operacion,
            mensaje=(
                f"🔴 La suma de costos NO coincide con el esperado. "
                f"Diferencia: ${diferencia:,.2f}"
            ),
            valor_esperado=f"${esperado:,.2f}",
            valor_obtenido=f"${calculado:,.2f}",
            accion_sugerida=(
                "Revisar la fórmula de distribución proporcional o "
                "el número de grupos detectados."
            ),
        ))
    
    return hallazgos


# ════════════════════════════════════════════════════════════
# REGLA 2: %POND / %PROPORTION SUMA 100% POR GRUPO
# ════════════════════════════════════════════════════════════
def validar_suma_porcentajes(
    operacion: str,
    detalle: pd.DataFrame,
    columna_grupo: str,
    columna_pct: str,
) -> List[Hallazgo]:
    """
    Verifica que la suma de %Pond/%Proportion = 100% por cada grupo
    (Reference o Container).
    
    Para CAPEX se permite que un contenedor sume 100% con un solo item.
    """
    hallazgos = []
    
    if columna_pct not in detalle.columns or columna_grupo not in detalle.columns:
        hallazgos.append(Hallazgo(
            regla="Suma de %Pond = 100%",
            severidad=Severidad.WARNING,
            operacion=operacion,
            mensaje=f"No se pueden validar porcentajes (columnas faltantes)",
        ))
        return hallazgos
    
    # Sumar porcentajes por grupo
    sumas = detalle.groupby(columna_grupo)[columna_pct].sum()
    grupos_invalidos = sumas[(sumas - 1.0).abs() > TOLERANCIA_PCT]
    
    if len(grupos_invalidos) == 0:
        hallazgos.append(Hallazgo(
            regla="Suma de %Pond = 100%",
            severidad=Severidad.OK,
            operacion=operacion,
            mensaje=(
                f"✅ Los porcentajes suman 100% en los {len(sumas)} grupos"
            ),
        ))
    else:
        # Mostrar máximo 5 grupos problemáticos
        ejemplos = []
        for grupo, suma in grupos_invalidos.head(5).items():
            ejemplos.append(f"{grupo}: {suma:.4%}")
        
        hallazgos.append(Hallazgo(
            regla="Suma de %Pond = 100%",
            severidad=Severidad.ERROR,
            operacion=operacion,
            mensaje=(
                f"🔴 {len(grupos_invalidos)} grupo(s) NO suman 100% en %Pond"
            ),
            detalle="Ejemplos: " + " | ".join(ejemplos),
            accion_sugerida=(
                "Revisar la fórmula de %Pond = Peso/Peso_Total_Grupo "
                "y la limpieza de datos del Bloque 2."
            ),
        ))
    
    return hallazgos


# ════════════════════════════════════════════════════════════
# REGLA 3: PESOS NO NEGATIVOS (excepto CAPEX)
# ════════════════════════════════════════════════════════════
def validar_pesos_no_negativos(
    operacion: str,
    detalle: pd.DataFrame,
    columna_peso: str,
    columna_es_capex: Optional[str] = None,
) -> List[Hallazgo]:
    """Detecta pesos negativos o cero (los CAPEX sí pueden ser 0)."""
    hallazgos = []
    
    if columna_peso not in detalle.columns:
        return hallazgos
    
    # Excluir CAPEX si la columna existe
    if columna_es_capex and columna_es_capex in detalle.columns:
        df_check = detalle[~detalle[columna_es_capex].fillna(False)]
    else:
        df_check = detalle
    
    pesos_negativos = df_check[df_check[columna_peso] < 0]
    pesos_cero = df_check[df_check[columna_peso] == 0]
    
    if len(pesos_negativos) == 0 and len(pesos_cero) == 0:
        hallazgos.append(Hallazgo(
            regla="Pesos válidos (>0)",
            severidad=Severidad.OK,
            operacion=operacion,
            mensaje=f"✅ Todos los pesos son positivos",
        ))
    else:
        if len(pesos_negativos) > 0:
            hallazgos.append(Hallazgo(
                regla="Pesos válidos (>0)",
                severidad=Severidad.ERROR,
                operacion=operacion,
                mensaje=f"🔴 {len(pesos_negativos)} fila(s) con peso NEGATIVO",
                accion_sugerida="Limpiar el reporte fuente antes de cargarlo.",
            ))
        if len(pesos_cero) > 0:
            hallazgos.append(Hallazgo(
                regla="Pesos válidos (>0)",
                severidad=Severidad.WARNING,
                operacion=operacion,
                mensaje=(
                    f"⚠️ {len(pesos_cero)} fila(s) con peso CERO "
                    f"(excluyendo CAPEX)"
                ),
                accion_sugerida=(
                    "Revisar si son items válidos o si falta el peso."
                ),
            ))
    
    return hallazgos


# ════════════════════════════════════════════════════════════
# REGLA 4: DUPLICADOS EN CLAVES PRIMARIAS
# ════════════════════════════════════════════════════════════
def validar_duplicados(
    operacion: str,
    detalle: pd.DataFrame,
    columnas_clave: List[str],
) -> List[Hallazgo]:
    """
    Detecta filas duplicadas en la combinación de columnas clave.
    Ejemplo: Sea → (Container Number, Item Code) no debería repetirse.
    """
    hallazgos = []
    
    cols_existentes = [c for c in columnas_clave if c in detalle.columns]
    if not cols_existentes:
        return hallazgos
    
    duplicados = detalle[detalle.duplicated(subset=cols_existentes, keep=False)]
    
    if len(duplicados) == 0:
        hallazgos.append(Hallazgo(
            regla="Sin duplicados",
            severidad=Severidad.OK,
            operacion=operacion,
            mensaje=f"✅ No hay duplicados en {cols_existentes}",
        ))
    else:
        hallazgos.append(Hallazgo(
            regla="Sin duplicados",
            severidad=Severidad.WARNING,
            operacion=operacion,
            mensaje=(
                f"⚠️ {len(duplicados)} fila(s) duplicada(s) en "
                f"{cols_existentes}"
            ),
            accion_sugerida=(
                "Revisar el reporte fuente. Los duplicados pueden causar "
                "doble conteo en %Pond."
            ),
        ))
    
    return hallazgos


# ════════════════════════════════════════════════════════════
# REGLA 5: BU ASIGNADO A TODAS LAS FILAS
# ════════════════════════════════════════════════════════════
def validar_bu_asignado(
    operacion: str,
    detalle: pd.DataFrame,
    columna_bu: str,
) -> List[Hallazgo]:
    """Verifica que todas las filas tengan un BU asignado (no nulo, no vacío)."""
    hallazgos = []
    
    if columna_bu not in detalle.columns:
        return hallazgos
    
    sin_bu = detalle[
        detalle[columna_bu].isna() | 
        (detalle[columna_bu].astype(str).str.strip() == "") |
        (detalle[columna_bu].astype(str).str.strip().str.upper() == "SINBU")
    ]
    
    if len(sin_bu) == 0:
        hallazgos.append(Hallazgo(
            regla="BU asignado en todas las filas",
            severidad=Severidad.OK,
            operacion=operacion,
            mensaje=f"✅ Todas las filas tienen BU asignado",
        ))
    else:
        hallazgos.append(Hallazgo(
            regla="BU asignado en todas las filas",
            severidad=Severidad.WARNING,
            operacion=operacion,
            mensaje=f"⚠️ {len(sin_bu)} fila(s) sin BU asignado",
            valor_obtenido=f"{len(sin_bu)} filas",
            accion_sugerida=(
                "Para Outbound: revisar formato del Reference. "
                "Para Land/Sea: completar la columna BU en el reporte."
            ),
        ))
    
    return hallazgos


# ════════════════════════════════════════════════════════════
# REGLA 6: VALIDACIÓN CRUZADA CAPEX vs REPORTE SEA
# ════════════════════════════════════════════════════════════
def validar_capex_cruzado(
    issues_capex: Dict[str, List[str]],
) -> List[Hallazgo]:
    """
    Verifica los issues detectados en el Bloque 4 sobre los CAPEX manuales:
    - Duplicados
    - Conflictos con contenedores del reporte
    - Datos inválidos
    """
    hallazgos = []
    
    if issues_capex.get("duplicados"):
        hallazgos.append(Hallazgo(
            regla="CAPEX sin duplicados",
            severidad=Severidad.ERROR,
            operacion="sea",
            mensaje=(
                f"🔴 Contenedores CAPEX duplicados: "
                f"{issues_capex['duplicados']}"
            ),
            accion_sugerida="Eliminar duplicados en la tabla CAPEX manual.",
        ))
    else:
        hallazgos.append(Hallazgo(
            regla="CAPEX sin duplicados",
            severidad=Severidad.OK,
            operacion="sea",
            mensaje="✅ No hay duplicados en contenedores CAPEX",
        ))
    
    if issues_capex.get("conflicto_con_reporte"):
        hallazgos.append(Hallazgo(
            regla="CAPEX no en reporte fuente",
            severidad=Severidad.CRITICAL,
            operacion="sea",
            mensaje=(
                f"🚨 CONFLICTO: Contenedores CAPEX que YA existen en el reporte: "
                f"{issues_capex['conflicto_con_reporte']}"
            ),
            accion_sugerida=(
                "ELIMINAR esos contenedores de la tabla CAPEX manual "
                "o del reporte. Causaría DOBLE CONTEO."
            ),
        ))
    else:
        hallazgos.append(Hallazgo(
            regla="CAPEX no en reporte fuente",
            severidad=Severidad.OK,
            operacion="sea",
            mensaje="✅ Contenedores CAPEX no conflictúan con el reporte",
        ))
    
    if issues_capex.get("invalidos"):
        hallazgos.append(Hallazgo(
            regla="CAPEX con datos completos",
            severidad=Severidad.WARNING,
            operacion="sea",
            mensaje=(
                f"⚠️ Registros CAPEX con datos incompletos: "
                f"{issues_capex['invalidos']}"
            ),
            accion_sugerida="Completar Container Number e Item Code.",
        ))
    
    return hallazgos


# ════════════════════════════════════════════════════════════
# REGLA 7: SUMMARY - %PCT POR FILA = 100%
# ════════════════════════════════════════════════════════════
def validar_pct_summary(metricas_summary: Dict) -> List[Hallazgo]:
    """Verifica que cada fila del Summary (Sea/Land/Outbound) sume 100% en %PCT."""
    hallazgos = []
    
    chequeos = [
        ("Sea %PCT",      metricas_summary.get("suma_pct_sea", 0)),
        ("Land %PCT",     metricas_summary.get("suma_pct_land", 0)),
        ("Outbound %PCT", metricas_summary.get("suma_pct_outbound", 0)),
    ]
    
    for nombre, suma in chequeos:
        if abs(suma - 1.0) <= TOLERANCIA_PCT or suma == 0:
            estado_ok = abs(suma - 1.0) <= TOLERANCIA_PCT
            hallazgos.append(Hallazgo(
                regla=f"{nombre} suma 100%",
                severidad=Severidad.OK if estado_ok else Severidad.INFO,
                operacion="summary",
                mensaje=(
                    f"✅ {nombre} suma {suma:.2%}" if estado_ok 
                    else f"ℹ️ {nombre} sin datos (suma = 0%)"
                ),
            ))
        else:
            hallazgos.append(Hallazgo(
                regla=f"{nombre} suma 100%",
                severidad=Severidad.ERROR,
                operacion="summary",
                mensaje=(
                    f"🔴 {nombre} suma {suma:.4%} (debería ser 100%)"
                ),
                valor_esperado="100%",
                valor_obtenido=f"{suma:.4%}",
                accion_sugerida=(
                    f"Revisar el cálculo en el Bloque 6 (Summary). "
                    f"Si es Sea, verifica que Capex/MCS estén siendo "
                    f"excluidos correctamente."
                ),
            ))
    
    return hallazgos


# ════════════════════════════════════════════════════════════
# REGLA 8: EXCLUSIÓN CAPEX/MCS EN %PCT SEA (regla crítica)
# ════════════════════════════════════════════════════════════
def validar_exclusion_capex_mcs(resultado_summary) -> List[Hallazgo]:
    """
    Verifica que Capex y MCS estén en %PCT Sea = 0% en el Summary.
    Esta es la regla crítica documentada en REGLAS_PROCESO líneas 65-67.
    """
    hallazgos = []
    
    if resultado_summary is None:
        return hallazgos
    
    tabla_pct = resultado_summary.tabla_pct
    
    if tabla_pct is None or len(tabla_pct) == 0:
        return hallazgos
    
    fila_sea = tabla_pct[tabla_pct["Type"] == "Sea %PCT"]
    if len(fila_sea) == 0:
        return hallazgos
    
    fila_sea = fila_sea.iloc[0]
    bus_excluidos_presentes = []
    
    for bu_excluido in ["Capex", "MCS"]:
        if bu_excluido in fila_sea.index:
            valor = fila_sea[bu_excluido]
            if isinstance(valor, (int, float)) and valor > TOLERANCIA_PCT:
                bus_excluidos_presentes.append(f"{bu_excluido}={valor:.2%}")
    
    if bus_excluidos_presentes:
        hallazgos.append(Hallazgo(
            regla="Exclusión Capex/MCS en %PCT Sea",
            severidad=Severidad.CRITICAL,
            operacion="summary",
            mensaje=(
                f"🚨 Capex/MCS aparecen en %PCT Sea (deben ser 0%): "
                f"{', '.join(bus_excluidos_presentes)}"
            ),
            accion_sugerida=(
                "Revisar el Bloque 4: la columna '%PCT (Summary)' debe "
                "asignar 0 a Capex y MCS."
            ),
        ))
    else:
        hallazgos.append(Hallazgo(
            regla="Exclusión Capex/MCS en %PCT Sea",
            severidad=Severidad.OK,
            operacion="summary",
            mensaje="✅ Capex y MCS correctamente excluidos del %PCT Sea",
        ))
    
    return hallazgos


# ════════════════════════════════════════════════════════════
# REGLA 9: COHERENCIA SEA - CONTENEDORES vs ITEMS
# ════════════════════════════════════════════════════════════
def validar_contenedores_sin_items(
    detalle_sea: pd.DataFrame,
    columna_container: str = "Container Number",
) -> List[Hallazgo]:
    """Detecta contenedores con 0 items (anomalía)."""
    hallazgos = []
    
    if columna_container not in detalle_sea.columns:
        return hallazgos
    
    items_por_container = detalle_sea.groupby(columna_container).size()
    vacios = items_por_container[items_por_container == 0]
    
    if len(vacios) == 0:
        hallazgos.append(Hallazgo(
            regla="Contenedores con items",
            severidad=Severidad.OK,
            operacion="sea",
            mensaje=f"✅ Todos los contenedores tienen al menos 1 item",
        ))
    else:
        hallazgos.append(Hallazgo(
            regla="Contenedores con items",
            severidad=Severidad.WARNING,
            operacion="sea",
            mensaje=f"⚠️ {len(vacios)} contenedor(es) sin items",
            accion_sugerida=(
                "Si son contenedores CAPEX, agregarlos a la tabla manual."
            ),
        ))
    
    return hallazgos


# ════════════════════════════════════════════════════════════
# REGLA 10: BUs INESPERADOS (no estándar y no especiales)
# ════════════════════════════════════════════════════════════
def validar_bus_conocidos(
    operacion: str,
    metricas: Dict,
    bus_conocidos: set,
) -> List[Hallazgo]:
    """Detecta BUs nuevos que no están en el catálogo."""
    hallazgos = []
    
    bus_detectados = set(metricas.get("bus_detectados", []))
    bus_nuevos = bus_detectados - bus_conocidos
    
    if not bus_nuevos:
        hallazgos.append(Hallazgo(
            regla="BUs conocidos",
            severidad=Severidad.OK,
            operacion=operacion,
            mensaje=f"✅ Todos los BUs están en el catálogo histórico",
        ))
    else:
        hallazgos.append(Hallazgo(
            regla="BUs conocidos",
            severidad=Severidad.WARNING,
            operacion=operacion,
            mensaje=(
                f"⚠️ BUs NUEVOS detectados: {sorted(bus_nuevos)}"
            ),
            accion_sugerida=(
                "Ir a la pestaña '🧠 BUs Detectados' para validarlos "
                "y agregarlos al catálogo."
            ),
        ))
    
    return hallazgos