"""Pestaña SEA: carga, CAPEX manual, procesamiento y resultados."""
import streamlit as st
import pandas as pd
from datetime import datetime

from src.ui.estado import Estado
from src.ingesta import cargar_sea
from src.ingesta.excepciones import (
    HojaNoEncontradaError, ColumnaFaltanteError, DatosVaciosError,
    ArchivoInvalidoError,
)
from src.procesamiento.procesar_sea import procesar_sea
from src.salida import generar_excel_solo_sea


def renderizar() -> None:
    """Renderiza la pestaña completa de SEA."""
    st.header("🚢 Importaciones Marítimas (SEA)")
    st.markdown(
        "Sube el reporte de **China Marítimos**. El sistema agrupa por "
        "`Container Number` y distribuye el costo fijo según el peso bruto. "
        "Los **contenedores CAPEX** se ingresan manualmente abajo."
    )
    
    # ═══════════════════════════════════════════════════════
    # SECCIÓN 1: CARGA DE ARCHIVO
    # ═══════════════════════════════════════════════════════
    col1, col2 = st.columns([3, 1])
    
    with col1:
        archivo = st.file_uploader(
            "📂 Selecciona el archivo Sea (.xlsx)",
            type=["xlsx", "xls"],
            key="upload_sea",
            help="Encabezados en fila 5. Columnas clave: BU, Item Code, Container Number, Total Gross Weight",
        )
    
    with col2:
        st.metric(
            "💰 Costo por contenedor",
            f"${st.session_state[Estado.COSTO_SEA]:,}",
        )
    
    # ═══════════════════════════════════════════════════════
    # SECCIÓN 2: CAPEX MANUAL
    # ═══════════════════════════════════════════════════════
    with st.expander("🔴 Contenedores CAPEX (ingreso manual)", expanded=False):
        st.warning(
            "⚠️ Los items CAPEX **no vienen** en el reporte fuente. "
            "Agrégalos aquí. Cada contenedor CAPEX absorbe el 100% del costo "
            f"(${st.session_state[Estado.COSTO_SEA]:,})."
        )
        
        capex_editado = st.data_editor(
            st.session_state[Estado.CAPEX_MANUAL],
            num_rows="dynamic",
            use_container_width=True,
            key="editor_capex",
            column_config={
                "Container Number": st.column_config.TextColumn(
                    "Container Number",
                    help="Ej: AMFU4236030",
                    required=True,
                ),
                "Item Code": st.column_config.TextColumn(
                    "Item Code",
                    help="Ej: CAPEX-08",
                    required=True,
                ),
            },
        )
        st.session_state[Estado.CAPEX_MANUAL] = capex_editado
        
        if len(capex_editado) > 0:
            st.success(f"✅ {len(capex_editado)} contenedor(es) CAPEX registrados")
    
    # ═══════════════════════════════════════════════════════
    # SECCIÓN 3: PROCESAR
    # ═══════════════════════════════════════════════════════
    if archivo is not None:
        st.session_state[Estado.NOMBRE_ARCH_SEA] = archivo.name
        st.success(f"✅ Archivo: **{archivo.name}**")
        
        col_btn1, col_btn2 = st.columns(2)
        
        with col_btn1:
            procesar = st.button(
                "🚀 Procesar SEA",
                type="primary",
                use_container_width=True,
                key="btn_procesar_sea",
            )
        
        if procesar:
            try:
                with st.spinner("Cargando archivo..."):
                    df_sea = cargar_sea(archivo)
                    st.session_state[Estado.DF_SEA_RAW] = df_sea
                
                with st.spinner("Procesando importaciones marítimas..."):
                    capex_list = st.session_state[Estado.CAPEX_MANUAL].to_dict("records")
                    capex_list = [c for c in capex_list 
                                  if c.get("Container Number") and c.get("Item Code")]
                    
                    resultado = procesar_sea(
                        df_sea,
                        contenedores_capex=capex_list,
                        costo_fijo=st.session_state[Estado.COSTO_SEA],
                    )
                    st.session_state[Estado.RES_SEA] = resultado
                
                st.success("✅ SEA procesado correctamente")
                st.rerun()
            
            except HojaNoEncontradaError as e:
                st.error(f"❌ No se encontró la hoja esperada")
                st.info(f"Hojas disponibles en tu archivo: {e.hojas_disponibles}")
            except ColumnaFaltanteError as e:
                st.error(f"❌ Faltan columnas obligatorias")
                st.info(f"Columnas faltantes: {', '.join(e.columnas_faltantes)}")
            except DatosVaciosError as e:
                st.error(f"❌ El archivo no contiene datos válidos: {e}")
            except ArchivoInvalidoError as e:
                st.error(f"❌ Archivo inválido: {e}")
            except Exception as e:
                st.exception(e)
    
    # ═══════════════════════════════════════════════════════
    # SECCIÓN 4: RESULTADOS
    # ═══════════════════════════════════════════════════════
    if st.session_state[Estado.RES_SEA] is not None:
        st.divider()
        st.subheader("📊 Resultados SEA")
        
        resultado = st.session_state[Estado.RES_SEA]
        metricas = resultado.metricas
        
        # Métricas principales
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("📦 Contenedores", metricas["total_contenedores"])
        c2.metric("📋 Items totales", f"{metricas['total_items']:,}")
        c3.metric("🔴 Items CAPEX", metricas["items_capex"])
        c4.metric("💵 Total USD", f"${metricas['costo_total_calculado']:,.0f}")
        
        # Validación de conservación
        if metricas["validacion_ok"]:
            st.success(
                f"✅ Validación OK: ${metricas['costo_total_calculado']:,.2f} = "
                f"{metricas['total_contenedores']} × ${st.session_state[Estado.COSTO_SEA]:,}"
            )
        else:
            st.error(
                f"❌ Validación FALLÓ: diferencia de "
                f"${metricas['diferencia_validacion']:,.2f}"
            )
        
        # Resumen por BU
        st.subheader("📋 Resumen por BU")
        st.caption("⚠️ Capex y MCS aparecen con sus montos, pero quedan excluidos del %PCT del Summary.")
        
        df_mostrar = resultado.resumen_bu.copy()
        st.dataframe(
            df_mostrar,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Amount (USD)":   st.column_config.NumberColumn(format="$%.0f"),
                "%PCT (Total)":   st.column_config.NumberColumn(format="%.2f%%"),
                "%PCT (Summary)": st.column_config.NumberColumn(format="%.2f%%"),
                "Peso Total (Kgs)": st.column_config.NumberColumn(format="%.2f"),
            },
        )
        
        # Tabla de contenedores
        with st.expander("📦 Ver tabla de contenedores"):
            st.dataframe(resultado.contenedores, use_container_width=True, hide_index=True)
        
        # Detalle completo
        with st.expander(f"🔍 Ver detalle completo ({len(resultado.detalle):,} filas)"):
            st.dataframe(resultado.detalle, use_container_width=True, hide_index=True)
        
        # Issues CAPEX
        if resultado.issues_capex.get("conflicto_con_reporte"):
            st.error(
                f"🚨 CONFLICTO: Contenedores CAPEX en el reporte: "
                f"{resultado.issues_capex['conflicto_con_reporte']}"
            )
        
        # Advertencias
        for adv in resultado.advertencias:
            st.warning(adv)
        
        # Descarga individual
        st.divider()
        buffer = generar_excel_solo_sea(resultado, st.session_state[Estado.COSTO_SEA])
        st.download_button(
            "📥 Descargar Sea.xlsx (solo esta hoja)",
            data=buffer,
            file_name=f"Sea_{datetime.now():%Y%m%d_%H%M}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )