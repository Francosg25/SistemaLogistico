"""Pestaña BUs: detección y validación de Business Units."""
import streamlit as st
import pandas as pd

from src.ui.estado import Estado
from src.reglas import (
    detectar_bus_actuales,
    comparar_con_historico,
    obtener_alertas_bu,
    obtener_catalogo,
)
from src.reglas.motor_reglas import registrar_bus_validados


def renderizar() -> None:
    """Renderiza la pestaña de detección y validación de BUs."""
    st.header("🧠 Detección y Validación de Business Units")
    st.markdown(
        "Aquí se muestran los BUs detectados en los datos cargados, "
        "comparados contra el catálogo histórico del sistema."
    )
    
    # ═══════════════════════════════════════════════════════
    # VALIDAR QUE HAYA DATOS
    # ═══════════════════════════════════════════════════════
    df_sea = st.session_state.get(Estado.DF_SEA_RAW)
    df_land = st.session_state.get(Estado.DF_LAND_RAW)
    df_out = st.session_state.get(Estado.DF_OUTBOUND_RAW)
    
    if not any([df_sea is not None, df_land is not None, df_out is not None]):
        st.info(
            "⚠️ Carga al menos un archivo en las pestañas **SEA, LAND u OUTBOUND** "
            "antes de validar BUs."
        )
        return
    
    # ═══════════════════════════════════════════════════════
    # DETECTAR Y COMPARAR
    # ═══════════════════════════════════════════════════════
    if st.button("🔍 Detectar BUs actuales", type="primary", use_container_width=True):
        with st.spinner("Detectando BUs en los datos..."):
            bus_actuales = detectar_bus_actuales(
                df_sea=df_sea,
                df_land=df_land,
                df_outbound=df_out,
            )
            comparacion = comparar_con_historico(bus_actuales)
            st.session_state[Estado.COMPARACION_BU] = comparacion
            st.rerun()
    
    # ═══════════════════════════════════════════════════════
    # MOSTRAR RESULTADOS
    # ═══════════════════════════════════════════════════════
    comparacion = st.session_state.get(Estado.COMPARACION_BU)
    if comparacion is None:
        return
    
    st.divider()
    
    # Métricas resumen
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🏷️ Total BUs", len(comparacion.bus_actuales))
    c2.metric("✨ Nuevos", len(comparacion.bus_nuevos),
              delta=len(comparacion.bus_nuevos) if comparacion.bus_nuevos else None)
    c3.metric("♻️ Recurrentes", len(comparacion.bus_recurrentes))
    c4.metric("👻 Desaparecidos", len(comparacion.bus_desaparecidos))
    
    # Tabla de BUs por operación
    st.subheader("📋 BUs detectados por operación")
    df_resumen = pd.DataFrame({
        "Operación": ["🚢 SEA", "🚚 LAND", "📤 OUTBOUND"],
        "BUs detectados": [
            ", ".join(sorted(comparacion.bus_por_operacion.get("sea", set()))) or "—",
            ", ".join(sorted(comparacion.bus_por_operacion.get("land", set()))) or "—",
            ", ".join(sorted(comparacion.bus_por_operacion.get("outbound", set()))) or "—",
        ],
    })
    st.dataframe(df_resumen, use_container_width=True, hide_index=True)
    
    # Alertas
    alertas = obtener_alertas_bu(comparacion)
    if alertas["errores"] or alertas["warnings"] or alertas["info"]:
        st.subheader("🚨 Alertas")
        for e in alertas["errores"]:
            st.error(e)
        for w in alertas["warnings"]:
            st.warning(w)
        for i in alertas["info"]:
            st.info(i)
    
    # ═══════════════════════════════════════════════════════
    # VALIDACIÓN MANUAL DE BUs NUEVOS
    # ═══════════════════════════════════════════════════════
    if comparacion.bus_nuevos:
        st.divider()
        st.subheader("✨ Validar BUs Nuevos")
        st.caption(
            "Los siguientes BUs **NO existen en el catálogo histórico**. "
            "Confírmalos para agregarlos al sistema."
        )
        
        for bu in sorted(comparacion.bus_nuevos):
            with st.expander(f"🆕 BU: **{bu}**", expanded=True):
                ops_donde = [
                    op for op in ["sea", "land", "outbound"]
                    if bu in comparacion.bus_por_operacion.get(op, set())
                ]
                st.markdown(f"Apareció en: **{', '.join(ops_donde)}**")
                
                col_a, col_b = st.columns(2)
                
                with col_a:
                    desc = st.text_input(
                        "Descripción",
                        value=f"Business Unit {bu}",
                        key=f"desc_{bu}",
                    )
                    operacion = st.selectbox(
                        "Operación principal",
                        ops_donde,
                        key=f"op_{bu}",
                    )
                
                with col_b:
                    es_std = st.checkbox(
                        "¿Es BU estándar (Mxx)?",
                        value=bu.startswith("M") and bu[1:].isdigit(),
                        key=f"std_{bu}",
                    )
                    incluir = st.checkbox(
                        "¿Incluir en %PCT del Summary?",
                        value=True,
                        key=f"inc_{bu}",
                    )
                
                if st.button(f"✅ Aprobar y registrar '{bu}'", key=f"btn_{bu}"):
                    n = registrar_bus_validados([{
                        "bu": bu,
                        "operacion": operacion,
                        "descripcion": desc,
                        "es_estandar": es_std,
                        "es_especial": not es_std,
                        "incluir_en_summary_pct": incluir,
                    }])
                    if n > 0:
                        st.success(f"✅ BU '{bu}' registrado en el catálogo")
                        # Limpiar comparación para forzar re-detección
                        st.session_state[Estado.COMPARACION_BU] = None
                        st.rerun()
