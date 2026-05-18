"""
Gestión centralizada del st.session_state.
Inicializa y administra todas las variables de estado de la app.
"""
import streamlit as st
import pandas as pd


# ============================================================
# CLAVES DEL ESTADO (constantes para evitar typos)
# ============================================================
class Estado:
    # Archivos raw (DataFrames cargados)
    DF_SEA_RAW       = "df_sea_raw"
    DF_LAND_RAW      = "df_land_raw"
    DF_OUTBOUND_RAW  = "df_outbound_raw"
    
    # Resultados procesados (objetos de los Bloques 3-6)
    RES_SEA          = "resultado_sea"
    RES_LAND         = "resultado_land"
    RES_OUTBOUND     = "resultado_outbound"
    RES_SUMMARY      = "resultado_summary"
    
    # Reporte de validación (Bloque 8)
    REPORTE_VAL      = "reporte_validacion"
    
    # CAPEX manual
    CAPEX_MANUAL     = "capex_manual"
    
    COSTOS_OUTBOUND_VARIABLES = "costos_outbound_variables"
    NOMBRE_ARCH_OUTBOUND = "nombre_archivo_outbound"
    
    # Comparación de BUs (Bloque 7)
    COMPARACION_BU   = "comparacion_bu"
    
    # Configuración de costos
    COSTO_SEA        = "costo_sea"
    COSTO_LAND       = "costo_land"
    COSTO_OUTBOUND   = "costo_outbound"
    
    # Nombres de archivos cargados
    NOMBRE_ARCH_SEA  = "nombre_archivo_sea"
    NOMBRE_ARCH_LAND = "nombre_archivo_land"
    NOMBRE_ARCH_OUT  = "nombre_archivo_outbound"


# ============================================================
# INICIALIZACIÓN
# ============================================================
def inicializar_estado() -> None:
    """Inicializa todas las variables de estado si no existen."""
    defaults = {
        # DataFrames
        Estado.DF_SEA_RAW:       None,
        Estado.DF_LAND_RAW:      None,
        Estado.DF_OUTBOUND_RAW:  None,
        
        # Resultados
        Estado.RES_SEA:          None,
        Estado.RES_LAND:         None,
        Estado.RES_OUTBOUND:     None,
        Estado.RES_SUMMARY:      None,
        Estado.REPORTE_VAL:      None,
        
        # CAPEX (Sea)
        Estado.CAPEX_MANUAL:     pd.DataFrame(
            columns=["Container Number", "Item Code"]
        ),
        
        # 🆕 Costos variables Outbound (tabla vacía editable)
        Estado.COSTOS_OUTBOUND_VARIABLES: pd.DataFrame(
            columns=["Reference", "Fix Cost"]
        ),
        
        # BUs
        Estado.COMPARACION_BU:   None,
        
        # Costos (defaults del config.yaml)
        Estado.COSTO_SEA:        2500,
        Estado.COSTO_LAND:       1200,
        Estado.COSTO_OUTBOUND:   1500,
        
        # Nombres de archivo
        Estado.NOMBRE_ARCH_SEA:  None,
        Estado.NOMBRE_ARCH_LAND: None,
        Estado.NOMBRE_ARCH_OUT:  None,
    }
    
    for key, default in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default


# ============================================================
# HELPERS
# ============================================================
def limpiar_todo() -> None:
    """Resetea todo el estado (botón 'Limpiar todo' del sidebar)."""
    claves_a_limpiar = [
        Estado.DF_SEA_RAW, Estado.DF_LAND_RAW, Estado.DF_OUTBOUND_RAW,
        Estado.RES_SEA, Estado.RES_LAND, Estado.RES_OUTBOUND,
        Estado.RES_SUMMARY, Estado.REPORTE_VAL,
        Estado.COMPARACION_BU,
        Estado.NOMBRE_ARCH_SEA, Estado.NOMBRE_ARCH_LAND, Estado.NOMBRE_ARCH_OUT,
    ]
    for clave in claves_a_limpiar:
        st.session_state[clave] = None
    
    # Reset de tablas editables
    st.session_state[Estado.CAPEX_MANUAL] = pd.DataFrame(
        columns=["Container Number", "Item Code"]
    )
    st.session_state[Estado.COSTOS_OUTBOUND_VARIABLES] = pd.DataFrame(
        columns=["Reference", "Fix Cost"]
    )


def estado_procesamiento() -> dict:
    """Retorna el estado actual de procesamiento de cada operación."""
    return {
        "sea":        st.session_state.get(Estado.RES_SEA) is not None,
        "land":       st.session_state.get(Estado.RES_LAND) is not None,
        "outbound":   st.session_state.get(Estado.RES_OUTBOUND) is not None,
        "summary":    st.session_state.get(Estado.RES_SUMMARY) is not None,
        "validacion": st.session_state.get(Estado.REPORTE_VAL) is not None,
    }


def todos_procesados() -> bool:
    """¿Están las 3 operaciones procesadas (listas para Summary)?"""
    estado = estado_procesamiento()
    return estado["sea"] and estado["land"] and estado["outbound"]