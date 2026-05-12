"""
Sidebar de la aplicación: configuración global y estado del proceso.
"""
import streamlit as st
from src.ui.estado import Estado, estado_procesamiento, limpiar_todo


def renderizar_sidebar() -> None:
    """Renderiza el sidebar completo."""
    with st.sidebar:
        # ─────────────────────────────────────────────────────
        # LOGO / TÍTULO
        # ─────────────────────────────────────────────────────
        st.title("📦 Consolidación")
        st.caption("Logística automatizada v1.0")
        st.divider()
        
        # ─────────────────────────────────────────────────────
        # CONFIGURACIÓN DE COSTOS FIJOS
        # ─────────────────────────────────────────────────────
        st.subheader("💰 Costos Fijos (USD)")
        st.caption("Modifica si los costos del periodo cambian.")
        
        st.session_state[Estado.COSTO_SEA] = st.number_input(
            "🚢 Sea (por contenedor)",
            min_value=0,
            value=int(st.session_state.get(Estado.COSTO_SEA, 2500)),
            step=100,
            help="Costo fijo USD por cada Container Number",
        )
        
        st.session_state[Estado.COSTO_LAND] = st.number_input(
            "🚚 Land (por reference)",
            min_value=0,
            value=int(st.session_state.get(Estado.COSTO_LAND, 1200)),
            step=100,
            help="Costo fijo USD por cada Reference terrestre",
        )
        
        st.session_state[Estado.COSTO_OUTBOUND] = st.number_input(
            "📤 Outbound (por reference)",
            min_value=0,
            value=int(st.session_state.get(Estado.COSTO_OUTBOUND, 1500)),
            step=100,
            help="Costo fijo USD por cada Reference de exportación",
        )
        
        st.divider()
        
        # ─────────────────────────────────────────────────────
        # ESTADO DEL PROCESO
        # ─────────────────────────────────────────────────────
        st.subheader("📊 Estado del proceso")
        estado = estado_procesamiento()
        
        def icono(activo: bool) -> str:
            return "✅" if activo else "⬜"
        
        st.markdown(f"{icono(estado['sea'])} **SEA** procesado")
        st.markdown(f"{icono(estado['land'])} **LAND** procesado")
        st.markdown(f"{icono(estado['outbound'])} **OUTBOUND** procesado")
        st.markdown(f"{icono(estado['summary'])} **SUMMARY** generado")
        st.markdown(f"{icono(estado['validacion'])} **VALIDACIONES** ejecutadas")
        
        st.divider()
        
        # ─────────────────────────────────────────────────────
        # BOTÓN DE LIMPIEZA
        # ─────────────────────────────────────────────────────
        if st.button("🗑️ Limpiar todo", use_container_width=True, type="secondary"):
            limpiar_todo()
            st.success("Estado limpiado")
            st.rerun()
        
        st.divider()
        
        # ─────────────────────────────────────────────────────
        # INFO
        # ─────────────────────────────────────────────────────
        st.caption(
            "ℹ️ Reglas: %PCT del Sea excluye Capex y MCS. "
            "Los BUs se detectan automáticamente."
        )