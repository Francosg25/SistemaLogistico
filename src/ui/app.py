"""
Interfaz Streamlit - Consolidación Logística
Carga independiente por tipo de operación: SEA, LAND, OUTBOUND
"""
import streamlit as st
import pandas as pd
from pathlib import Path
from io import BytesIO
from datetime import datetime

# === Importaciones de módulos internos (a desarrollar en bloques siguientes) ===
# from src.ingesta.lector_excel import cargar_sea, cargar_land, cargar_outbound
# from src.procesamiento.procesar_sea import procesar_sea
# from src.procesamiento.procesar_land import procesar_land
# from src.procesamiento.procesar_outbound import procesar_outbound
# from src.procesamiento.generar_summary import generar_summary
# from src.salida.generar_excel import exportar_resultado

# ============================================================
# CONFIGURACIÓN DE LA PÁGINA
# ============================================================
st.set_page_config(
    page_title="Consolidación Logística",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================
# ESTADO DE SESIÓN (mantiene datos entre interacciones)
# ============================================================
if "resultado_sea" not in st.session_state:
    st.session_state.resultado_sea = None
if "resultado_land" not in st.session_state:
    st.session_state.resultado_land = None
if "resultado_outbound" not in st.session_state:
    st.session_state.resultado_outbound = None
if "capex_manual" not in st.session_state:
    st.session_state.capex_manual = pd.DataFrame(
        columns=["Container Number", "Item Code"]
    )

# ============================================================
# ENCABEZADO
# ============================================================
st.title("📦 Consolidación Logística")
st.caption(f"Versión 1.0  |  {datetime.now().strftime('%d/%m/%Y %H:%M')}")

# ============================================================
# SIDEBAR - Configuración global
# ============================================================
with st.sidebar:
    st.header("⚙️ Configuración Global")
    
    st.subheader("💰 Costos fijos (USD)")
    costo_sea = st.number_input(
        "Sea (por contenedor)", 
        min_value=0, 
        value=2500, 
        step=100
    )
    costo_land = st.number_input(
        "Land (por reference)", 
        min_value=0, 
        value=1200, 
        step=100
    )
    costo_outbound = st.number_input(
        "Outbound (por reference)", 
        min_value=0, 
        value=1500, 
        step=100
    )
    
    st.divider()
    
    st.subheader("📊 Estado del proceso")
    estado_sea = "✅" if st.session_state.resultado_sea is not None else "⬜"
    estado_land = "✅" if st.session_state.resultado_land is not None else "⬜"
    estado_out = "✅" if st.session_state.resultado_outbound is not None else "⬜"
    st.markdown(f"{estado_sea} SEA procesado")
    st.markdown(f"{estado_land} LAND procesado")
    st.markdown(f"{estado_out} OUTBOUND procesado")
    
    st.divider()
    
    if st.button("🗑️ Limpiar todo", use_container_width=True):
        for key in ["resultado_sea", "resultado_land", "resultado_outbound"]:
            st.session_state[key] = None
        st.session_state.capex_manual = pd.DataFrame(
            columns=["Container Number", "Item Code"]
        )
        st.rerun()

# ============================================================
# PESTAÑAS PRINCIPALES
# ============================================================
tab_sea, tab_land, tab_outbound, tab_summary = st.tabs([
    "🚢 SEA (Marítimo)",
    "🚚 LAND (Terrestre)",
    "📤 OUTBOUND (Exportación)",
    "📊 SUMMARY (Consolidado)"
])

# ════════════════════════════════════════════════════════════
# PESTAÑA 1: SEA
# ════════════════════════════════════════════════════════════
with tab_sea:
    st.header("🚢 Importaciones Marítimas")
    st.markdown(
        "Sube el reporte de **China Marítimos**. "
        "El sistema agrupa por `Container Number` y distribuye el costo "
        "fijo según el peso bruto de cada item."
    )
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        archivo_sea = st.file_uploader(
            "📂 Archivo Sea (.xlsx)",
            type=["xlsx", "xls"],
            key="upload_sea",
            help="Encabezados en fila 5. Columnas clave: BU, Item Code, Container Number, Total Gross Weight"
        )
    
    with col2:
        st.metric("Costo por contenedor", f"${costo_sea:,}")
    
    # === CAPEX manual ===
    with st.expander("🔴 Contenedores CAPEX (ingreso manual)", expanded=False):
        st.markdown(
            "Los items CAPEX **no vienen** en el reporte fuente. "
            "Agrégalos aquí. Cada contenedor CAPEX absorbe el 100% del costo ($2,500)."
        )
        
        capex_editado = st.data_editor(
            st.session_state.capex_manual,
            num_rows="dynamic",
            use_container_width=True,
            key="editor_capex",
            column_config={
                "Container Number": st.column_config.TextColumn(
                    "Container Number",
                    help="Ej: AMFU4236030",
                    required=True
                ),
                "Item Code": st.column_config.TextColumn(
                    "Item Code",
                    help="Ej: CAPEX-08",
                    required=True
                ),
            }
        )
        st.session_state.capex_manual = capex_editado
    
    # === Botón procesar ===
    if archivo_sea is not None:
        st.success(f"✅ Archivo cargado: **{archivo_sea.name}**")
        
        if st.button("🚀 Procesar SEA", type="primary", use_container_width=True):
            with st.spinner("Procesando importaciones marítimas..."):
                # === AQUÍ se conecta con los módulos del Bloque 4 ===
                # df_sea = cargar_sea(archivo_sea)
                # resultado = procesar_sea(
                #     df_sea, 
                #     contenedores_capex=st.session_state.capex_manual.to_dict('records'),
                #     costo_fijo=costo_sea
                # )
                # st.session_state.resultado_sea = resultado
                
                # Placeholder mientras se implementa Bloque 4:
                st.session_state.resultado_sea = {"placeholder": True}
                st.success("✅ SEA procesado correctamente")
    
    # === Mostrar resultados ===
    if st.session_state.resultado_sea is not None:
        st.divider()
        st.subheader("📊 Resultados SEA")
        
        col_a, col_b, col_c = st.columns(3)
        col_a.metric("Contenedores", "22")
        col_b.metric("Total USD", "$132,500")
        col_c.metric("Items procesados", "1,217")
        
        # Aquí se mostrarán los DataFrames reales del resultado:
        # st.dataframe(st.session_state.resultado_sea['detalle'])
        # st.dataframe(st.session_state.resultado_sea['resumen_bu'])
        
        st.download_button(
            "📥 Descargar Sea.xlsx",
            data=b"placeholder",  # Reemplazar con BytesIO del Excel real
            file_name=f"Sea_Procesado_{datetime.now():%Y%m%d}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

# ════════════════════════════════════════════════════════════
# PESTAÑA 2: LAND
# ════════════════════════════════════════════════════════════
with tab_land:
    st.header("🚚 Importaciones Terrestres")
    st.markdown(
        "Sube el reporte **Land**. Se agrupa por `Reference` y se distribuye "
        "el costo fijo proporcional al peso bruto."
    )
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        archivo_land = st.file_uploader(
            "📂 Archivo Land (.xlsx)",
            type=["xlsx", "xls"],
            key="upload_land",
            help="Encabezados en fila 5. Columnas clave: Reference, BU, Peso Bruto (Kgs), No. Parte Prov."
        )
    
    with col2:
        st.metric("Costo por reference", f"${costo_land:,}")
    
    if archivo_land is not None:
        st.success(f"✅ Archivo cargado: **{archivo_land.name}**")
        
        if st.button("🚀 Procesar LAND", type="primary", use_container_width=True):
            with st.spinner("Procesando importaciones terrestres..."):
                # === Conexión con Bloque 5 ===
                # df_land = cargar_land(archivo_land)
                # resultado = procesar_land(df_land, costo_fijo=costo_land)
                # st.session_state.resultado_land = resultado
                
                st.session_state.resultado_land = {"placeholder": True}
                st.success("✅ LAND procesado correctamente")
    
    if st.session_state.resultado_land is not None:
        st.divider()
        st.subheader("📊 Resultados LAND")
        
        col_a, col_b, col_c = st.columns(3)
        col_a.metric("References", "9")
        col_b.metric("Total USD", "$10,800")
        col_c.metric("Items procesados", "134")
        
        st.download_button(
            "📥 Descargar Land.xlsx",
            data=b"placeholder",
            file_name=f"Land_Procesado_{datetime.now():%Y%m%d}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

# ════════════════════════════════════════════════════════════
# PESTAÑA 3: OUTBOUND
# ════════════════════════════════════════════════════════════
with tab_outbound:
    st.header("📤 Exportaciones")
    st.markdown(
        "Sube el reporte **Outbound**. El sistema **infiere el BU** del patrón "
        "del Reference (ej: `FG-R-2208LE26.M46/M45` → BU = `M45`)."
    )
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        archivo_out = st.file_uploader(
            "📂 Archivo Outbound (.xlsx)",
            type=["xlsx", "xls"],
            key="upload_out",
            help="Encabezados en fila 8. Columnas clave: Reference, Waybill Number, Gross Weight, Item"
        )
    
    with col2:
        st.metric("Costo por reference", f"${costo_outbound:,}")
    
    if archivo_out is not None:
        st.success(f"✅ Archivo cargado: **{archivo_out.name}**")
        
        if st.button("🚀 Procesar OUTBOUND", type="primary", use_container_width=True):
            with st.spinner("Procesando exportaciones..."):
                # === Conexión con Bloque 3 ===
                # df_out = cargar_outbound(archivo_out)
                # resultado = procesar_outbound(df_out, costo_fijo=costo_outbound)
                # st.session_state.resultado_outbound = resultado
                
                st.session_state.resultado_outbound = {"placeholder": True}
                st.success("✅ OUTBOUND procesado correctamente")
    
    if st.session_state.resultado_outbound is not None:
        st.divider()
        st.subheader("📊 Resultados OUTBOUND")
        
        col_a, col_b, col_c = st.columns(3)
        col_a.metric("References", "7")
        col_b.metric("Total USD", "$10,500")
        col_c.metric("Items procesados", "82")
        
        st.download_button(
            "📥 Descargar Outbound.xlsx",
            data=b"placeholder",
            file_name=f"Outbound_Procesado_{datetime.now():%Y%m%d}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

# ════════════════════════════════════════════════════════════
# PESTAÑA 4: SUMMARY
# ════════════════════════════════════════════════════════════
with tab_summary:
    st.header("📊 Summary Consolidado")
    st.markdown(
        "Una vez procesados **SEA, LAND y OUTBOUND**, aquí se genera la tabla "
        "consolidada por Business Unit. Recuerda: `Capex` y `MCS` se excluyen "
        "del cálculo de `%PCT` en Sea."
    )
    
    # === Validar que los 3 estén procesados ===
    listos = [
        ("SEA", st.session_state.resultado_sea),
        ("LAND", st.session_state.resultado_land),
        ("OUTBOUND", st.session_state.resultado_outbound),
    ]
    
    faltantes = [nombre for nombre, res in listos if res is None]
    
    if faltantes:
        st.warning(
            f"⚠️ Faltan por procesar: **{', '.join(faltantes)}**. "
            f"Ve a las pestañas correspondientes para cargarlos."
        )
    else:
        st.success("✅ Todos los módulos están procesados. Puedes generar el Summary.")
        
        if st.button("🧮 Generar Summary Consolidado", type="primary", use_container_width=True):
            with st.spinner("Consolidando resultados..."):
                # === Conexión con Bloque 6 ===
                # summary = generar_summary(
                #     st.session_state.resultado_outbound,
                #     st.session_state.resultado_sea,
                #     st.session_state.resultado_land
                # )
                # st.session_state.summary = summary
                
                st.success("✅ Summary generado")
        
        st.divider()
        st.subheader("📋 Vista previa del Summary")
        
        # Placeholder con la estructura esperada:
        df_preview = pd.DataFrame({
            "Type": ["Sea %PCT", "Land %PCT", "Outbound %PCT"],
            "M01": ["15%", "0%", "21%"],
            "M19": ["49%", "18%", "41%"],
            "M23": ["3%", "34%", "3%"],
            "M45": ["29%", "5%", "32%"],
            "M46": ["3%", "43%", "3%"],
        })
        st.dataframe(df_preview, use_container_width=True, hide_index=True)
        
        st.divider()
        
        col_dl1, col_dl2 = st.columns(2)
        with col_dl1:
            st.download_button(
                "📥 Descargar Summary.xlsx",
                data=b"placeholder",
                file_name=f"Summary_{datetime.now():%Y%m%d}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        with col_dl2:
            st.download_button(
                "📦 Descargar Reporte COMPLETO (4 hojas)",
                data=b"placeholder",
                file_name=f"Consolidado_{datetime.now():%Y%m%d}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=True
            )

# ============================================================
# FOOTER
# ============================================================
st.divider()
st.caption("📦 Consolidación Logística v1.0 | Desarrollado para automatizar costos de fletes")