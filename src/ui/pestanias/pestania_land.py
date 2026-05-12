"""Pestaña LAND: carga, procesamiento y resultados."""
import streamlit as st
from datetime import datetime

from src.ui.estado import Estado
from src.ingesta import cargar_land
from src.ingesta.excepciones import (
    HojaNoEncontradaError, ColumnaFaltanteError, DatosVaciosError,
    ArchivoInvalidoError,
)
from src.procesamiento.procesar_land import procesar_land
from src.salida import generar_excel_solo_land


def renderizar() -> None:
    """Renderiza la pestaña completa de LAND."""
    st.header("🚚 Importaciones Terrestres (LAND)")
    st.markdown(
        "Sube el reporte **Land**. Se agrupa por `Reference` y se distribuye "
        "el costo fijo proporcional al peso bruto. Los BUs especiales "
        "(`Machine`, `Miscelaneus`) se incluyen en el Summary."
    )
    
    # ═══════════════════════════════════════════════════════
    # CARGA
    # ═══════════════════════════════════════════════════════
    col1, col2 = st.columns([3, 1])
    
    with col1:
        archivo = st.file_uploader(
            "📂 Selecciona el archivo Land (.xlsx)",
            type=["xlsx", "xls"],
            key="upload_land",
            help="Encabezados en fila 5. Columnas clave: Reference, BU, Peso Bruto (Kgs), No. Parte Prov.",
        )
    
    with col2:
        st.metric(
            "💰 Costo por reference",
            f"${st.session_state[Estado.COSTO_LAND]:,}",
        )
    
    # ═══════════════════════════════════════════════════════
    # PROCESAR
    # ═══════════════════════════════════════════════════════
    if archivo is not None:
        st.session_state[Estado.NOMBRE_ARCH_LAND] = archivo.name
        st.success(f"✅ Archivo: **{archivo.name}**")
        
        if st.button("🚀 Procesar LAND", type="primary", use_container_width=True, key="btn_procesar_land"):
            try:
                with st.spinner("Cargando archivo..."):
                    df_land = cargar_land(archivo)
                    st.session_state[Estado.DF_LAND_RAW] = df_land
                
                with st.spinner("Procesando importaciones terrestres..."):
                    resultado = procesar_land(
                        df_land,
                        costo_fijo=st.session_state[Estado.COSTO_LAND],
                    )
                    st.session_state[Estado.RES_LAND] = resultado
                
                st.success("✅ LAND procesado correctamente")
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
    if st.session_state[Estado.RES_LAND] is not None:
        st.divider()
        st.subheader("📊 Resultados LAND")
        
        resultado = st.session_state[Estado.RES_LAND]
        metricas = resultado.metricas
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("📋 References", metricas["total_references"])
        c2.metric("🧾 Items", metricas["total_items"])
        c3.metric("🏷️ BUs", metricas["total_bus"])
        c4.metric("💵 Total USD", f"${metricas['costo_total_calculado']:,.0f}")
        
        if metricas["validacion_ok"]:
            st.success(
                f"✅ Validación OK: ${metricas['costo_total_calculado']:,.2f} = "
                f"{metricas['total_references']} × ${st.session_state[Estado.COSTO_LAND]:,}"
            )
        
        if metricas["bus_especiales"]:
            st.info(
                f"ℹ️ BUs especiales detectados: **{', '.join(metricas['bus_especiales'])}**. "
                f"Estos se incluyen en el Summary."
            )
        
        # Resumen por BU
        st.subheader("📋 Resumen por BU")
        st.dataframe(
            resultado.resumen_bu,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Monto Total (USD)":  st.column_config.NumberColumn(format="$%.2f"),
                "%PCT":               st.column_config.NumberColumn(format="%.2f%%"),
                "Peso Total (Kgs)":   st.column_config.NumberColumn(format="%.2f"),
            },
        )
        
        # References
        with st.expander("📦 Ver tabla de References"):
            st.dataframe(resultado.resumen_referencias, use_container_width=True, hide_index=True)
        
        # Detalle
        with st.expander(f"🔍 Ver detalle ({len(resultado.detalle):,} filas)"):
            st.dataframe(resultado.detalle, use_container_width=True, hide_index=True)
        
        for adv in resultado.advertencias:
            st.warning(adv)
        
        # Descarga
        st.divider()
        buffer = generar_excel_solo_land(resultado, st.session_state[Estado.COSTO_LAND])
        st.download_button(
            "📥 Descargar Land.xlsx",
            data=buffer,
            file_name=f"Land_{datetime.now():%Y%m%d_%H%M}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )