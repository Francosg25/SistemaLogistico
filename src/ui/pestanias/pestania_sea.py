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
            help=(
                "El sistema detecta automáticamente la hoja y la fila de "
                "encabezado. Columnas requeridas: Container, Peso Bruto, Item."
            ),
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
                    # Limpiar CAPEX vacíos
                    capex_list = st.session_state[Estado.CAPEX_MANUAL].to_dict("records")
                    capex_list = [
                        c for c in capex_list
                        if c.get("Container Number") and c.get("Item Code")
                    ]

                    resultado = procesar_sea(
                        df_sea,
                        contenedores_capex=capex_list,
                        costo_fijo=st.session_state[Estado.COSTO_SEA],
                    )
                    st.session_state[Estado.RES_SEA] = resultado

                st.success("✅ SEA procesado correctamente")
                st.rerun()

            except HojaNoEncontradaError as e:
                st.error("❌ No se encontró la hoja esperada")
                hojas_disp = getattr(e, "hojas_disponibles", None)
                if hojas_disp:
                    st.info(f"Hojas disponibles en tu archivo: {hojas_disp}")
            except ColumnaFaltanteError as e:
                faltantes = getattr(e, "columnas_faltantes", [])
                st.error("❌ Faltan columnas obligatorias")
                st.info(f"Columnas faltantes: {', '.join(faltantes)}")
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

        # ───────────────────────────────────────────────────
        # MÉTRICAS PRINCIPALES (con .get() defensivo)
        # ───────────────────────────────────────────────────
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("📦 Contenedores", metricas.get("total_contenedores", 0))
        c2.metric("📋 Items totales", f"{metricas.get('total_items', 0):,}")
        c3.metric("🔴 Items CAPEX", metricas.get("items_capex", 0))
        c4.metric(
            "💵 Total USD",
            f"${metricas.get('costo_total_calculado', 0):,.0f}",
        )

        # ───────────────────────────────────────────────────
        # VALIDACIÓN DE CUADRE
        # ───────────────────────────────────────────────────
        if metricas.get("validacion_ok"):
            st.success(
                f"✅ Validación OK: "
                f"${metricas.get('costo_total_calculado', 0):,.2f} = "
                f"{metricas.get('total_contenedores', 0)} × "
                f"${st.session_state[Estado.COSTO_SEA]:,}"
            )
        elif metricas.get("diferencia_validacion", 0) > 1:
            st.error(
                f"❌ Validación FALLÓ: diferencia de "
                f"${metricas.get('diferencia_validacion', 0):,.2f}"
            )

        # ───────────────────────────────────────────────────
        # BUs ESPECIALES Y BUs NUEVOS
        # ───────────────────────────────────────────────────
        bus_especiales = metricas.get("bus_especiales", [])
        bus_nuevos = metricas.get("bus_nuevos", [])

        if bus_especiales:
            st.info(
                f"ℹ️ BUs especiales detectados: **{', '.join(bus_especiales)}**. "
                f"Capex y MCS quedan excluidos del %PCT del Summary."
            )

        if bus_nuevos:
            st.warning(
                f"🆕 BUs nuevos detectados: **{', '.join(bus_nuevos)}**. "
                f"Verifica si son válidos."
            )

        # ───────────────────────────────────────────────────
        # RESUMEN POR BU
        # ───────────────────────────────────────────────────
        st.subheader("📋 Resumen por BU")
        st.caption(
            "⚠️ Capex y MCS aparecen con sus montos, pero quedan excluidos "
            "del %PCT del Summary."
        )

        df_mostrar = resultado.resumen_bu.copy()
        st.dataframe(
            df_mostrar,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Amount (USD)":     st.column_config.NumberColumn(format="$%.0f"),
                "%PCT (Total)":     st.column_config.NumberColumn(format="%.2f%%"),
                "%PCT (Summary)":   st.column_config.NumberColumn(format="%.2f%%"),
                "%PCT":             st.column_config.NumberColumn(format="%.2f%%"),
                "Peso Total (Kgs)": st.column_config.NumberColumn(format="%.2f"),
            },
        )

        # ───────────────────────────────────────────────────
        # TABLA DE CONTENEDORES
        # ───────────────────────────────────────────────────
        with st.expander("📦 Ver tabla de contenedores"):
            st.dataframe(
                resultado.contenedores,
                use_container_width=True,
                hide_index=True,
            )

        # ───────────────────────────────────────────────────
        # 🔄 SECCIÓN DE AUDITORÍA: Items reasignados a Miscelaneus
        # ───────────────────────────────────────────────────
        reporte_misc = getattr(resultado, "reporte_miscelaneus", None) or {}
        items_reasignados = reporte_misc.get("items_reasignados", 0)

        if items_reasignados > 0:
            st.subheader("🔄 Regla Miscelaneus aplicada")

            m1, m2, m3 = st.columns(3)
            m1.metric("📦 Items reasignados", items_reasignados)
            m2.metric(
                "💵 Monto reasignado",
                f"${reporte_misc.get('monto_reasignado', 0):,.2f}",
            )

            bus_origen = reporte_misc.get("bus_origen_reasignados", [])
            m3.metric(
                "🏷️ BUs origen",
                ", ".join(bus_origen) if bus_origen else "—",
            )

            with st.expander("🔍 Ver items reasignados a Miscelaneus"):
                df_detalle = reporte_misc.get("detalle")

                if df_detalle is not None and len(df_detalle) > 0:
                    # Detectar columnas dinámicamente
                    columnas_preferidas = [
                        "Container Number",
                        "Container",
                        "Item Code",
                        "Item",
                        "BU",
                        "BU Final",
                        "Total Gross Weight",
                        "Peso Bruto",
                        "Amount",
                    ]
                    columnas_mostrar = [
                        c for c in columnas_preferidas
                        if c in df_detalle.columns
                    ]

                    if not columnas_mostrar:
                        columnas_mostrar = list(df_detalle.columns)

                    st.dataframe(
                        df_detalle[columnas_mostrar],
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "Amount": st.column_config.NumberColumn(format="$%.2f"),
                            "Total Gross Weight": st.column_config.NumberColumn(format="%.2f"),
                            "Peso Bruto": st.column_config.NumberColumn(format="%.2f"),
                        },
                    )

                    st.caption(
                        "ℹ️ Items detectados por palabras clave "
                        "(PLASTIC, CHAROLA, TAPA sin guion, BASE sin guion, "
                        "CAJA sin guion). Configurable en `config.yaml`."
                    )
                else:
                    st.info("No hay detalle disponible.")

        # ───────────────────────────────────────────────────
        # DETALLE COMPLETO
        # ───────────────────────────────────────────────────
        with st.expander(f"🔍 Ver detalle completo ({len(resultado.detalle):,} filas)"):
            st.dataframe(
                resultado.detalle,
                use_container_width=True,
                hide_index=True,
            )

        # ───────────────────────────────────────────────────
        # ISSUES CAPEX
        # ───────────────────────────────────────────────────
        issues_capex = getattr(resultado, "issues_capex", {}) or {}
        if issues_capex.get("conflicto_con_reporte"):
            st.error(
                f"🚨 CONFLICTO: Contenedores CAPEX en el reporte: "
                f"{issues_capex['conflicto_con_reporte']}"
            )

        if issues_capex.get("contenedores_no_encontrados"):
            st.warning(
                f"⚠️ Contenedores CAPEX no encontrados en reporte: "
                f"{issues_capex['contenedores_no_encontrados']}"
            )

        # ───────────────────────────────────────────────────
        # ADVERTENCIAS
        # ───────────────────────────────────────────────────
        for adv in resultado.advertencias:
            st.warning(adv)

        # ───────────────────────────────────────────────────
        # DESCARGA
        # ───────────────────────────────────────────────────
        st.divider()
        buffer = generar_excel_solo_sea(
            resultado,
            st.session_state[Estado.COSTO_SEA],
        )
        st.download_button(
            "📥 Descargar Sea.xlsx (solo esta hoja)",
            data=buffer,
            file_name=f"Sea_{datetime.now():%Y%m%d_%H%M}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )