"""Pestaña VALIDACIONES: ejecuta y muestra el reporte de control de calidad."""
import streamlit as st
import pandas as pd

from src.ui.estado import Estado
from src.validaciones import validar_todo, Severidad


def renderizar() -> None:
    """Renderiza la pestaña de validaciones."""
    st.header("✅ Validaciones Automáticas")
    st.markdown(
        "Reporte de control de calidad sobre los datos procesados. "
        "Ejecuta las 10 reglas de validación: conservación de costo, "
        "duplicados, reglas CAPEX, exclusión Capex/MCS, etc."
    )
    
    # ═══════════════════════════════════════════════════════
    # EJECUTAR VALIDACIONES
    # ═══════════════════════════════════════════════════════
    hay_datos = any([
        st.session_state.get(Estado.RES_SEA),
        st.session_state.get(Estado.RES_LAND),
        st.session_state.get(Estado.RES_OUTBOUND),
    ])
    
    if not hay_datos:
        st.info("⚠️ Procesa al menos una operación antes de validar.")
        return
    
    if st.button("🔍 Ejecutar validaciones", type="primary", use_container_width=True):
        with st.spinner("Ejecutando 10 reglas de validación..."):
            reporte = validar_todo(
                resultado_outbound=st.session_state.get(Estado.RES_OUTBOUND),
                resultado_sea=st.session_state.get(Estado.RES_SEA),
                resultado_land=st.session_state.get(Estado.RES_LAND),
                resultado_summary=st.session_state.get(Estado.RES_SUMMARY),
            )
            st.session_state[Estado.REPORTE_VAL] = reporte
        st.rerun()
    
    # ═══════════════════════════════════════════════════════
    # MOSTRAR REPORTE
    # ═══════════════════════════════════════════════════════
    reporte = st.session_state.get(Estado.REPORTE_VAL)
    if reporte is None:
        return
    
    st.divider()
    
    resumen = reporte.resumen()
    estado = resumen["estado_global"]
    emoji = resumen["emoji_global"]
    
    # Banner de estado global
    if estado == "OK":
        st.success(f"## {emoji} Estado global: **OK** — Listo para exportar")
    elif estado == "WARNING":
        st.warning(f"## {emoji} Estado global: **WARNING** — Revisa antes de exportar")
    elif estado in ("ERROR", "CRITICAL"):
        st.error(f"## {emoji} Estado global: **{estado}** — NO exportar sin resolver")
    else:
        st.info(f"## {emoji} Estado global: **{estado}**")
    
    # Métricas
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📊 Total checks", resumen["total_validaciones"])
    c2.metric("🟢 OK", resumen["ok"])
    c3.metric("🟡 Warnings", resumen["warnings"])
    c4.metric("🔴 Errores", resumen["errores"])
    
    if not resumen["puede_exportar"]:
        st.error(
            "🚨 **NO se recomienda exportar el Excel** porque hay errores críticos. "
            "Resuélvelos antes de continuar."
        )
    
    # ═══════════════════════════════════════════════════════
    # FILTROS
    # ═══════════════════════════════════════════════════════
    st.divider()
    col_f1, col_f2 = st.columns(2)
    
    with col_f1:
        filtro_sev = st.multiselect(
            "Filtrar por severidad",
            options=["OK", "INFO", "WARNING", "ERROR", "CRITICAL"],
            default=["WARNING", "ERROR", "CRITICAL"],
        )
    with col_f2:
        filtro_op = st.multiselect(
            "Filtrar por operación",
            options=["sea", "land", "outbound", "summary", "general"],
            default=["sea", "land", "outbound", "summary"],
        )
    
    # Tabla de hallazgos
    hallazgos = [
        h for h in reporte.hallazgos
        if h.severidad.value in filtro_sev and h.operacion in filtro_op
    ]
    
    if hallazgos:
        df = pd.DataFrame([h.to_dict() for h in hallazgos])
        df_mostrar = df[["emoji", "operacion", "regla", "mensaje", "accion_sugerida"]].copy()
        df_mostrar.columns = ["", "Operación", "Regla", "Mensaje", "Acción Sugerida"]
        st.dataframe(df_mostrar, use_container_width=True, hide_index=True)
    else:
        st.info("✅ No hay hallazgos con los filtros seleccionados.")