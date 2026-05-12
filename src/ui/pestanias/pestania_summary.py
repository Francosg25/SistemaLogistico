"""Pestaña SUMMARY: consolidación final y descarga del Excel completo."""
import streamlit as st
import pandas as pd
from datetime import datetime

from src.ui.estado import Estado, todos_procesados
from src.procesamiento.generar_summary import generar_summary
from src.salida import generar_excel_completo


def renderizar() -> None:
    """Renderiza la pestaña SUMMARY."""
    st.header("📊 SUMMARY Consolidado")
    st.markdown(
        "Una vez procesados **SEA, LAND y OUTBOUND**, aquí se genera la tabla "
        "consolidada por Business Unit. Recuerda: `Capex` y `MCS` se **excluyen** "
        "del cálculo de `%PCT` en Sea (regla del negocio)."
    )
    
    # ═══════════════════════════════════════════════════════
    # VALIDAR QUE LOS 3 ESTÉN PROCESADOS
    # ═══════════════════════════════════════════════════════
    if not todos_procesados():
        listos = {
            "🚢 SEA":      st.session_state[Estado.RES_SEA] is not None,
            "🚚 LAND":     st.session_state[Estado.RES_LAND] is not None,
            "📤 OUTBOUND": st.session_state[Estado.RES_OUTBOUND] is not None,
        }
        faltantes = [nombre for nombre, ok in listos.items() if not ok]
        
        st.warning(
            f"⚠️ Faltan por procesar: **{', '.join(faltantes)}**. "
            f"Ve a las pestañas correspondientes para cargarlos."
        )
        
        # Mostrar estado actual
        df_estado = pd.DataFrame({
            "Operación": list(listos.keys()),
            "Estado": ["✅ Procesado" if v else "⬜ Pendiente" for v in listos.values()],
        })
        st.dataframe(df_estado, use_container_width=True, hide_index=True)
        return
    
    # ═══════════════════════════════════════════════════════
    # GENERAR SUMMARY
    # ═══════════════════════════════════════════════════════
    st.success("✅ Todos los módulos procesados. Listo para consolidar.")
    
    if st.button("🧮 Generar Summary Consolidado", type="primary", use_container_width=True):
        with st.spinner("Consolidando resultados..."):
            summary = generar_summary(
                st.session_state[Estado.RES_OUTBOUND],
                st.session_state[Estado.RES_SEA],
                st.session_state[Estado.RES_LAND],
            )
            st.session_state[Estado.RES_SUMMARY] = summary
        
        st.success("✅ Summary generado correctamente")
        st.rerun()
    
    # ═══════════════════════════════════════════════════════
    # MOSTRAR RESULTADOS DEL SUMMARY
    # ═══════════════════════════════════════════════════════
    summary = st.session_state.get(Estado.RES_SUMMARY)
    if summary is None:
        return
    
    st.divider()
    
    # Métricas principales
    metricas = summary.metricas
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🚢 Sea Total",      f"${metricas['total_sea_usd']:,.0f}")
    c2.metric("🚚 Land Total",     f"${metricas['total_land_usd']:,.0f}")
    c3.metric("📤 Outbound Total", f"${metricas['total_outbound_usd']:,.0f}")
    c4.metric("🎯 GRAN TOTAL",     f"${metricas['gran_total_usd']:,.0f}")
    
    # Tabla de %PCT
    st.subheader("📊 Distribución %PCT por BU")
    st.caption("⚠️ Capex y MCS están EXCLUIDOS del %PCT de Sea (regla del negocio)")
    
    bus_pct = [bu for bu in summary.bus_orden if bu not in ("Capex", "MCS")]
    
    # 🔧 FIX: Los valores vienen como 0.21 (= 21%). Streamlit los formatea con %
    column_config_pct = {
        bu: st.column_config.NumberColumn(
            format="%.1f%%",  # Formato % con 1 decimal
            help=f"Porcentaje del BU {bu} respecto al total"
        ) 
        for bu in bus_pct
    }
    
    # Multiplicar por 100 para que el formato % funcione correctamente
    tabla_pct_mostrar = summary.tabla_pct.copy()
    for col in tabla_pct_mostrar.columns:
        if col != "Type":
            tabla_pct_mostrar[col] = tabla_pct_mostrar[col] * 100
    
    st.dataframe(
        tabla_pct_mostrar,
        use_container_width=True,
        hide_index=True,
        column_config=column_config_pct,
    )
    
    # Tabla de montos
    st.subheader("💵 Montos por BU (Arg. Var $)")
    st.caption("Los montos incluyen TODOS los BUs (Capex y MCS también).")
    
    column_config_montos = {
        col: st.column_config.NumberColumn(format="$%.0f")
        for col in summary.tabla_montos.columns if col not in ("Viewer", "Arg. Var $")
    }
    column_config_montos["Arg. Var $"] = st.column_config.NumberColumn(format="$%.0f")
    
    st.dataframe(
        summary.tabla_montos,
        use_container_width=True,
        hide_index=True,
        column_config=column_config_montos,
    )
    
    # Vista consolidada
    with st.expander("🔍 Vista consolidada completa"):
        column_config_consol = {
            col: st.column_config.NumberColumn(format="$%.2f")
            for col in summary.tabla_consolidada.columns if "Monto" in col or "TOTAL" in col
        }
        column_config_consol.update({
            col: st.column_config.NumberColumn(format="%.2f%%")
            for col in summary.tabla_consolidada.columns if "%PCT" in col
        })
        st.dataframe(
            summary.tabla_consolidada,
            use_container_width=True,
            hide_index=True,
            column_config=column_config_consol,
        )
    
    # Alertas
    if metricas.get("bus_nuevos"):
        st.info(
            f"ℹ️ BUs no estándar este mes: **{', '.join(metricas['bus_nuevos'])}**. "
            "Recuerda: los BUs pueden cambiar mes a mes."
        )
    
    for adv in summary.advertencias:
        st.warning(adv)
    
    # ═══════════════════════════════════════════════════════
    # DESCARGA DEL EXCEL COMPLETO
    # ═══════════════════════════════════════════════════════
    st.divider()
    st.subheader("📦 Descargar Reporte Final")
    
    col_dl1, col_dl2 = st.columns(2)
    
    with col_dl1:
        if st.button("📥 Generar Excel COMPLETO", type="primary", use_container_width=True):
            with st.spinner("Generando Excel..."):
                buffer = generar_excel_completo(
                    resultado_outbound=st.session_state[Estado.RES_OUTBOUND],
                    resultado_sea=st.session_state[Estado.RES_SEA],
                    resultado_land=st.session_state[Estado.RES_LAND],
                    resultado_summary=summary,
                    reporte_validacion=st.session_state.get(Estado.REPORTE_VAL),
                    costos={
                        "outbound": st.session_state[Estado.COSTO_OUTBOUND],
                        "sea":      st.session_state[Estado.COSTO_SEA],
                        "land":     st.session_state[Estado.COSTO_LAND],
                    },
                )
                # Guardar buffer en session_state para que persista
                st.session_state["excel_buffer"] = buffer
            st.success("✅ Excel generado. Haz clic en el botón de descarga ↘️")
    
    with col_dl2:
        if "excel_buffer" in st.session_state:
            st.download_button(
                "⬇️ Descargar Consolidado.xlsx",
                data=st.session_state["excel_buffer"],
                file_name=f"Consolidacion_Logistica_{datetime.now():%Y%m%d_%H%M}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=True,
            )
