"""Pestaña OUTBOUND: carga, procesamiento y resultados (con costos variables)."""
import streamlit as st
from datetime import datetime

from src.ui.estado import Estado
from src.ingesta import cargar_outbound
from src.ingesta.excepciones import (
    HojaNoEncontradaError, ColumnaFaltanteError, DatosVaciosError,
    ArchivoInvalidoError,
)
from src.procesamiento import procesar_outbound
from src.salida import generar_excel_solo_outbound


def renderizar() -> None:
    """Renderiza la pestaña completa de OUTBOUND."""
    st.header("📤 Exportaciones (OUTBOUND)")
    st.markdown(
        "Sube el reporte **Outbound**. El sistema lee también la **tabla de "
        "costos variables** (columnas BC:BE) para usar el costo correcto por "
        "cada Reference."
    )
    
    # ═══════════════════════════════════════════════════════
    # CARGA
    # ═══════════════════════════════════════════════════════
    col1, col2, col3 = st.columns([3, 1, 1])
    
    with col1:
        archivo = st.file_uploader(
            "📂 Selecciona el archivo Outbound (.xlsx)",
            type=["xlsx", "xls"],
            key="upload_out",
            help="Sección Extraction: columnas BG-BO, fila 8. Tabla costos: BC-BE, fila 8.",
        )
    
    with col2:
        modo_costo = st.radio(
            "💰 Modo de costo",
            options=["Variable", "Fijo"],
            index=0,
            help="Variable: usa la tabla BC:BE del archivo. Fijo: usa el valor del sidebar.",
        )
    
    with col3:
        st.metric(
            "💵 Costo fallback",
            f"${st.session_state[Estado.COSTO_OUTBOUND]:,}",
        )
    
    # ═══════════════════════════════════════════════════════
    # PROCESAR
    # ═══════════════════════════════════════════════════════
    if archivo is not None:
        st.session_state[Estado.NOMBRE_ARCH_OUT] = archivo.name
        st.success(f"✅ Archivo: **{archivo.name}**")
        
        if st.button("🚀 Procesar OUTBOUND", type="primary", use_container_width=True, key="btn_procesar_out"):
            try:
                with st.spinner("Cargando archivo y tabla de costos..."):
                    df_out, df_costos = cargar_outbound(archivo)
                    st.session_state[Estado.DF_OUTBOUND_RAW] = df_out
                    
                    # Guardar tabla de costos en sesión
                    if df_costos is not None:
                        st.session_state["df_costos_outbound"] = df_costos
                        st.info(
                            f"💰 Tabla de costos detectada: **{len(df_costos)} references** "
                            f"con `Fix Cost` total = **${df_costos['Fix Cost'].sum():,.0f}**"
                        )
                
                with st.spinner("Procesando exportaciones..."):
                    # Decidir si usar costos variables o fijos
                    df_costos_a_usar = df_costos if modo_costo == "Variable" else None
                    
                    resultado = procesar_outbound(
                        df_out,
                        costo_fijo=st.session_state[Estado.COSTO_OUTBOUND],
                        df_costos=df_costos_a_usar,  # 🆕
                    )
                    st.session_state[Estado.RES_OUTBOUND] = resultado
                
                st.success("✅ OUTBOUND procesado correctamente")
                st.rerun()
            
            except HojaNoEncontradaError as e:
                st.error("❌ No se encontró la hoja esperada")
                st.info(f"Hojas disponibles: {e.hojas_disponibles}")
            except ColumnaFaltanteError as e:
                st.error(f"❌ Faltan columnas: {', '.join(e.columnas_faltantes)}")
            except DatosVaciosError as e:
                st.error(f"❌ Archivo sin datos válidos: {e}")
            except ArchivoInvalidoError as e:
                st.error(f"❌ Archivo inválido: {e}")
            except Exception as e:
                st.exception(e)
    
    # ═══════════════════════════════════════════════════════
    # RESULTADOS
    # ═══════════════════════════════════════════════════════
    if st.session_state[Estado.RES_OUTBOUND] is not None:
        st.divider()
        st.subheader("📊 Resultados OUTBOUND")
        
        resultado = st.session_state[Estado.RES_OUTBOUND]
        metricas = resultado.metricas
        
        # 🆕 Mostrar modo de costo
        modo_emoji = "📊" if metricas["modo_costo"] == "variable" else "💵"
        st.info(f"{modo_emoji} **Modo de costo:** {metricas['modo_costo'].upper()}")
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("📋 References", metricas["total_references"])
        c2.metric("🧾 Items", metricas["total_items"])
        c3.metric("🏷️ BUs detectados", metricas["total_bus"])
        c4.metric("💵 Total USD", f"${metricas['costo_total_calculado']:,.0f}")
        
        # Validación
        if metricas["validacion_ok"]:
            st.success(
                f"✅ Validación OK: Calculado ${metricas['costo_total_calculado']:,.2f} ≈ "
                f"Esperado ${metricas['costo_total_esperado']:,.2f}"
            )
        else:
            st.warning(
                f"⚠️ Diferencia de ${metricas['diferencia_validacion']:,.2f} entre "
                f"calculado y esperado. Revisa redondeos."
            )
        
        st.info(f"🧠 **BUs detectados:** {', '.join(metricas['bus_detectados'])}")
        
        # 🆕 Tabla de costos si está disponible
        if "df_costos_outbound" in st.session_state and metricas["modo_costo"] == "variable":
            with st.expander("💰 Tabla de costos por Reference (BC:BE del archivo)"):
                df_costos = st.session_state["df_costos_outbound"]
                st.dataframe(
                    df_costos,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Cost (USD)": st.column_config.NumberColumn(format="$%.2f"),
                        "Fix Cost":   st.column_config.NumberColumn(format="$%.2f"),
                    },
                )
        
        # Resumen por BU
        st.subheader("📋 Resumen por BU")
        st.dataframe(
            resultado.resumen_bu,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Log. Exp (USD)":   st.column_config.NumberColumn(format="$%.2f"),
                "%PCT":             st.column_config.NumberColumn(format="%.2f%%"),
                "Peso Total (Kgs)": st.column_config.NumberColumn(format="%.2f"),
            },
        )
        
        # Tabla de References
        with st.expander("📦 Ver tabla de References"):
            st.dataframe(
                resultado.referencias,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Fix Cost":         st.column_config.NumberColumn(format="$%.2f"),
                    "Total Calculado":  st.column_config.NumberColumn(format="$%.2f"),
                    "Peso Total (Kgs)": st.column_config.NumberColumn(format="%.2f"),
                },
            )
        
        # Detalle
        with st.expander(f"🔍 Ver detalle ({len(resultado.detalle):,} filas)"):
            st.dataframe(resultado.detalle, use_container_width=True, hide_index=True)
        
        for adv in resultado.advertencias:
            st.warning(adv)
        
        # Descarga
        st.divider()
        buffer = generar_excel_solo_outbound(resultado, st.session_state[Estado.COSTO_OUTBOUND])
        st.download_button(
            "📥 Descargar Outbound.xlsx",
            data=buffer,
            file_name=f"Outbound_{datetime.now():%Y%m%d_%H%M}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )