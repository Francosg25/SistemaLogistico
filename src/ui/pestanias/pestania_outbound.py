"""Pestaña OUTBOUND: carga, costos variables, procesamiento y resultados."""
import streamlit as st
import pandas as pd
from datetime import datetime

from src.ui.estado import Estado
from src.ingesta import cargar_outbound
from src.ingesta.excepciones import (
    HojaNoEncontradaError, ColumnaFaltanteError, DatosVaciosError,
    ArchivoInvalidoError,
)
from src.procesamiento.procesar_outbound import procesar_outbound
from src.salida import generar_excel_solo_outbound


def renderizar() -> None:
    """Renderiza la pestaña completa de OUTBOUND."""
    st.header("📤 Exportaciones (OUTBOUND)")
    st.markdown(
        "Sube el reporte **Outbound** (REPORTE EXPO). El sistema agrupa por "
        "`Waybill Number` y distribuye el costo fijo proporcional al peso bruto. "
        "El **BU se infiere del patrón del Waybill** (último `Mxx` si hay varios)."
    )

    # ═══════════════════════════════════════════════════════
    # SECCIÓN 1: CARGA DE ARCHIVO
    # ═══════════════════════════════════════════════════════
    col1, col2 = st.columns([3, 1])

    with col1:
        archivo = st.file_uploader(
            "📂 Selecciona el archivo Outbound (.xlsx)",
            type=["xlsx", "xls"],
            key="upload_outbound",
            help=(
                "El sistema detecta automáticamente la hoja y la fila de "
                "encabezado. Columnas requeridas: Reference (Waybill), "
                "Peso Bruto, Item."
            ),
        )

    with col2:
        st.metric(
            "💰 Costo default por Waybill",
            f"${st.session_state[Estado.COSTO_OUTBOUND]:,}",
        )

    # ═══════════════════════════════════════════════════════
    # SECCIÓN 2: COSTOS VARIABLES (opcional)
    # ═══════════════════════════════════════════════════════
    with st.expander("💰 Costos variables por Waybill (opcional)", expanded=False):
        st.info(
            "ℹ️ Si algún Waybill tiene un costo distinto al default "
            f"(${st.session_state[Estado.COSTO_OUTBOUND]:,}), agrégalo aquí. "
            "Sino, se aplicará el costo default a TODOS."
        )

        # Inicializar editor si no existe
        if Estado.COSTOS_OUTBOUND_VARIABLES not in st.session_state:
            st.session_state[Estado.COSTOS_OUTBOUND_VARIABLES] = pd.DataFrame(
                columns=["Reference", "Fix Cost"]
            )

        costos_editado = st.data_editor(
            st.session_state[Estado.COSTOS_OUTBOUND_VARIABLES],
            num_rows="dynamic",
            use_container_width=True,
            key="editor_costos_outbound",
            column_config={
                "Reference": st.column_config.TextColumn(
                    "Reference (Waybill)",
                    help="Ej: FG-R-2180LE25.M46-M45",
                    required=True,
                ),
                "Fix Cost": st.column_config.NumberColumn(
                    "Fix Cost ($)",
                    help="Costo personalizado para este Waybill",
                    min_value=0,
                    format="$%.2f",
                    required=True,
                ),
            },
        )
        st.session_state[Estado.COSTOS_OUTBOUND_VARIABLES] = costos_editado

        if len(costos_editado) > 0:
            st.success(f"✅ {len(costos_editado)} costos variables registrados")

    # ═══════════════════════════════════════════════════════
    # SECCIÓN 3: PROCESAR
    # ═══════════════════════════════════════════════════════
    if archivo is not None:
        st.session_state[Estado.NOMBRE_ARCH_OUTBOUND] = archivo.name
        st.success(f"✅ Archivo: **{archivo.name}**")

        if st.button(
            "🚀 Procesar OUTBOUND",
            type="primary",
            use_container_width=True,
            key="btn_procesar_outbound",
        ):
            try:
                with st.spinner("Cargando archivo..."):
                    df_out, df_costos_archivo = cargar_outbound(archivo)
                    st.session_state[Estado.DF_OUTBOUND_RAW] = df_out

                # Decidir qué tabla de costos usar
                df_costos_manual = st.session_state.get(
                    Estado.COSTOS_OUTBOUND_VARIABLES
                )
                df_costos_manual_valido = (
                    df_costos_manual is not None
                    and len(df_costos_manual) > 0
                    and df_costos_manual["Reference"].notna().any()
                )

                if df_costos_manual_valido:
                    df_costos_a_usar = df_costos_manual.dropna(
                        subset=["Reference", "Fix Cost"]
                    )
                    st.info(
                        f"💡 Usando tabla manual de costos variables "
                        f"({len(df_costos_a_usar)} entradas)"
                    )
                elif df_costos_archivo is not None and len(df_costos_archivo) > 0:
                    df_costos_a_usar = df_costos_archivo
                    st.info(
                        f"💡 Usando tabla de costos del archivo "
                        f"({len(df_costos_archivo)} entradas)"
                    )
                else:
                    df_costos_a_usar = None

                with st.spinner("Procesando exportaciones..."):
                    resultado = procesar_outbound(
                        df_out,
                        costo_fijo=st.session_state[Estado.COSTO_OUTBOUND],
                        df_costos=df_costos_a_usar,
                    )
                    st.session_state[Estado.RES_OUTBOUND] = resultado

                st.success("✅ OUTBOUND procesado correctamente")
                st.rerun()

            except HojaNoEncontradaError as e:
                st.error("❌ No se encontró la hoja esperada")
                hojas_disp = getattr(e, "hojas_disponibles", None)
                if hojas_disp:
                    st.info(f"Hojas disponibles: {hojas_disp}")
            except ColumnaFaltanteError as e:
                faltantes = getattr(e, "columnas_faltantes", [])
                st.error(f"❌ Faltan columnas: {', '.join(faltantes)}")
            except DatosVaciosError as e:
                st.error(f"❌ Archivo sin datos válidos: {e}")
            except ArchivoInvalidoError as e:
                st.error(f"❌ Archivo inválido: {e}")
            except Exception as e:
                st.exception(e)

    # ═══════════════════════════════════════════════════════
    # SECCIÓN 4: RESULTADOS
    # ═══════════════════════════════════════════════════════
    if st.session_state[Estado.RES_OUTBOUND] is not None:
        st.divider()
        st.subheader("📊 Resultados OUTBOUND")

        resultado = st.session_state[Estado.RES_OUTBOUND]
        metricas = resultado.metricas

        # ───────────────────────────────────────────────────
        # MÉTRICAS PRINCIPALES (con .get() defensivo)
        # 🔧 FIX: Usar 'total_waybills' (no 'total_references')
        # ───────────────────────────────────────────────────
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("📋 Waybills", metricas.get("total_waybills", 0))
        c2.metric("🧾 Items", metricas.get("total_items", 0))
        c3.metric("🏷️ BUs", metricas.get("total_bus", 0))
        c4.metric(
            "💵 Total USD",
            f"${metricas.get('costo_total_calculado', 0):,.0f}",
        )

        # ───────────────────────────────────────────────────
        # MODO DE COSTO (variable / default)
        # ───────────────────────────────────────────────────
        modo_costo = metricas.get("modo_costo", "default")
        modo_emoji = "📊" if modo_costo == "variable" else "💵"
        n_variables = metricas.get("n_waybills_variables", 0)
        n_default = metricas.get("n_waybills_default", 0)

        if modo_costo == "variable":
            st.info(
                f"{modo_emoji} **Modo costo variable**: "
                f"{n_variables} waybill(s) con costo personalizado, "
                f"{n_default} con costo default."
            )
        else:
            st.info(
                f"{modo_emoji} **Modo costo default**: todos los waybills "
                f"a ${st.session_state[Estado.COSTO_OUTBOUND]:,}."
            )

        # ───────────────────────────────────────────────────
        # VALIDACIÓN DE CUADRE
        # ───────────────────────────────────────────────────
        if metricas.get("validacion_ok"):
            st.success(
                f"✅ Validación OK: "
                f"${metricas.get('costo_total_calculado', 0):,.2f} = "
                f"${metricas.get('costo_total_esperado', 0):,.2f} (esperado)"
            )
        elif metricas.get("diferencia_validacion", 0) > 1:
            st.error(
                f"❌ Validación FALLÓ: diferencia de "
                f"${metricas.get('diferencia_validacion', 0):,.2f}"
            )

        # ───────────────────────────────────────────────────
        # BUs ESPECIALES Y NUEVOS
        # ───────────────────────────────────────────────────
        bus_especiales = metricas.get("bus_especiales", [])
        bus_nuevos = metricas.get("bus_nuevos", [])

        if bus_especiales:
            st.info(
                f"ℹ️ BUs especiales detectados: **{', '.join(bus_especiales)}**. "
                f"Estos se incluyen en el Summary."
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
        st.dataframe(
            resultado.resumen_bu,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Monto Total (USD)":  st.column_config.NumberColumn(format="$%.2f"),
                "%PCT":               st.column_config.NumberColumn(format="percent"),
                "Peso Total (Kgs)":   st.column_config.NumberColumn(format="%.2f"),
            },
        )

        # ───────────────────────────────────────────────────
        # TABLA DE WAYBILLS
        # ───────────────────────────────────────────────────
        with st.expander("📦 Ver tabla de Waybills"):
            st.dataframe(
                resultado.resumen_waybills,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Fix Cost":         st.column_config.NumberColumn(format="$%.2f"),
                    "Total Amount":     st.column_config.NumberColumn(format="$%.2f"),
                    "Peso Total (Kgs)": st.column_config.NumberColumn(format="%.2f"),
                },
            )

        # ───────────────────────────────────────────────────
        # 🔄 SECCIÓN AUDITORÍA: Items reasignados a Miscelaneus
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
                    columnas_preferidas = [
                        "Reference",
                        "Waybill Number",
                        "Customer",
                        "Item",
                        "Item Code",
                        "BU",
                        "BU Final",
                        "Peso Bruto",
                        "Gross Weight",
                        "Calc_Exp",
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
                            "Calc_Exp":     st.column_config.NumberColumn(format="$%.2f"),
                            "Amount":       st.column_config.NumberColumn(format="$%.2f"),
                            "Peso Bruto":   st.column_config.NumberColumn(format="%.2f"),
                            "Gross Weight": st.column_config.NumberColumn(format="%.2f"),
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
        with st.expander(f"🔍 Ver detalle completo ({len(resultado.df_detalle):,} filas)"):
            st.dataframe(
                resultado.df_detalle,
                use_container_width=True,
                hide_index=True,
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
        buffer = generar_excel_solo_outbound(
            resultado,
            st.session_state[Estado.COSTO_OUTBOUND],
        )
        st.download_button(
            "📥 Descargar Outbound.xlsx",
            data=buffer,
            file_name=f"Outbound_{datetime.now():%Y%m%d_%H%M}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )