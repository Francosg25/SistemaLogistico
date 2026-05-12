"""Pestaña OUTBOUND: carga, procesamiento y resultados."""
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
        "Sube el reporte **Outbound**. El sistema **infiere el BU** del patrón "
        "del Reference. Ejemplo: `FG-R-2208LE26.M46/M45` → BU = `M45` (segundo)."
    )
    
    # ═══════════════════════════════════════════════════════
    # CARGA
    # ═══════════════════════════════════════════════════════
    col1, col2 = st.columns([3, 1])
    
    with col1:
        archivo = st.file_uploader(
            "📂 Selecciona el archivo Outbound (.xlsx)",
            type=["xlsx", "xls"],
            key="upload_out",
            help="Encabezados en fila 8. Columnas clave: Reference, Waybill Number, Gross Weight, Item",
        )
    
    with col2:
        st.metric(
            "💰 Costo por reference",
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
                with st.spinner("Cargando archivo..."):
                    df_out = cargar_outbound(archivo)
                    st.session_state[Estado.DF_OUTBOUND_RAW] = df_out
                
                with st.spinner("Procesando exportaciones..."):
                    resultado = procesar_outbound(
                        df_out,
                        costo_fijo=st.session_state[Estado.COSTO_OUTBOUND],
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
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("📋 References", metricas["total_references"])
        c2.metric("🧾 Items", metricas["total_items"])
        c3.metric("🏷️ BUs inferidos", metricas["total_bus"])
        c4.metric("💵 Total USD", f"${metricas['costo_total_calculado']:,.0f}")
        
        if metricas["validacion_ok"]:
            st.success(
                f"✅ Validación OK: ${metricas['costo_total_calculado']:,.2f} = "
                f"{metricas['total_references']} × ${st.session_state[Estado.COSTO_OUTBOUND]:,}"
            )
        
        st.info(f"🧠 **BUs inferidos del Reference:** {', '.join(metricas['bus_detectados'])}")
        
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
        
        # Tabla de References con BU asignado
        with st.expander("📦 Ver tabla de References (con BU inferido)"):
            st.dataframe(resultado.referencias, use_container_width=True, hide_index=True)
        
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