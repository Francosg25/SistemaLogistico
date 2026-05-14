import streamlit as st
from datetime import datetime

from src.ui.estado import inicializar_estado
from src.ui.sidebar import renderizar_sidebar
from src.ui.pestanias import (
    pestania_sea,
    pestania_land,
    pestania_outbound,
    pestania_bus,
    pestania_summary,
    pestania_validaciones,
)



st.set_page_config(
    page_title="Consolidación Logística",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get Help": None,
        "Report a bug": None,
        "About": "Consolidación Logística v1.0 - Software de automatización.",
    },
)


# ============================================================
# CSS PERSONALIZADO (opcional, mejora visual)
# ============================================================
st.markdown("""
    <style>
    .stMetric {
        background-color: #f8f9fa;
        padding: 12px;
        border-radius: 8px;
        border-left: 4px solid #1F4E78;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        font-weight: 600;
    }
    .stTabs [aria-selected="true"] {
        background-color: #DDEBF7;
    }
    </style>
""", unsafe_allow_html=True)


# ============================================================
# INICIALIZAR ESTADO
# ============================================================
inicializar_estado()


# ============================================================
# ENCABEZADO PRINCIPAL
# ============================================================
col_titulo, col_fecha = st.columns([3, 1])
with col_titulo:
    st.title("📦 Consolidación Logística")
    st.caption("Automatización de costos de fletes — Outbound · Sea · Land")
with col_fecha:
    st.metric("📅 Fecha", datetime.now().strftime("%d/%m/%Y"))


# ============================================================
# SIDEBAR
# ============================================================
renderizar_sidebar()


# ============================================================
# PESTAÑAS PRINCIPALES
# ============================================================
tab_sea, tab_land, tab_out, tab_bus, tab_summary, tab_val = st.tabs([
    "🚢 SEA",
    "🚚 LAND",
    "📤 OUTBOUND",
    "🧠 BUs",
    "📊 SUMMARY",
    "✅ VALIDACIONES",
])

with tab_sea:
    pestania_sea.renderizar()

with tab_land:
    pestania_land.renderizar()

with tab_out:
    pestania_outbound.renderizar()

with tab_bus:
    pestania_bus.renderizar()

with tab_summary:
    pestania_summary.renderizar()

with tab_val:
    pestania_validaciones.renderizar()


# ============================================================
# FOOTER
# ============================================================
st.divider()
st.caption(
    f"📦 Consolidación Logística v1.0 | "
    f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')} | "
    f"Desarrollado para automatizar costos de fletes"
)