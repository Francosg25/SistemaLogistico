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
            help=(
                "El sistema detecta automáticamente la hoja correcta y la fila "
                "de encabezado. Columnas requeridas: Reference, Peso Bruto, Item."
            ),
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

        if st.button(
            "🚀 Procesar LAND",
            type="primary",
            use_container_width=True,
            key="btn_procesar_land",
        ):
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
    # RESULTADOS
    # ═══════════════════════════════════════════════════════
    if st.session_state[Estado.RES_LAND] is not None:
        st.divider()
        st.subheader("📊 Resultados LAND")

        resultado = st.session_state[Estado.RES_LAND]
        metricas = resultado.metricas

        # ───────────────────────────────────────────────────
        # MÉTRICAS PRINCIPALES (usando .get para evitar KeyError)
        # ───────────────────────────────────────────────────
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("📋 References", metricas.get("total_references", 0))
        c2.metric("🧾 Items", metricas.get("total_items", 0))
        c3.metric("🏷️ BUs", metricas.get("total_bus", 0))
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
                f"{metricas.get('total_references', 0)} × "
                f"${st.session_state[Estado.COSTO_LAND]:,}"
            )
        elif metricas.get("diferencia_validacion", 0) > 1:
            st.warning(
                f"⚠️ Diferencia de "
                f"${metricas.get('diferencia_validacion', 0):,.2f} entre "
                f"costo esperado y calculado."
            )

        # ───────────────────────────────────────────────────
        # BUs ESPECIALES (Miscelaneus, Machine, Sin Asignar)
        # ───────────────────────────────────────────────────
        bus_especiales = metricas.get("bus_especiales", [])
        if bus_especiales:
            st.info(
                f"ℹ️ BUs especiales detectados: **{', '.join(bus_especiales)}**. "
                f"Estos se incluyen en el Summary."
            )

        # ───────────────────────────────────────────────────
        # BUs NUEVOS (no estándar)
        # ───────────────────────────────────────────────────
        bus_nuevos = metricas.get("bus_nuevos", [])
        if bus_nuevos:
            st.warning(
                f"🆕 BUs nuevos detectados (no estaban en el catálogo): "
                f"**{', '.join(bus_nuevos)}**. Verifica si son válidos."
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
                "%PCT":               st.column_config.NumberColumn(format="%.2f%%"),
                "Peso Total (Kgs)":   st.column_config.NumberColumn(format="%.2f"),
            },
        )

        # ───────────────────────────────────────────────────
        # TABLA DE REFERENCES
        # ───────────────────────────────────────────────────
        with st.expander("📦 Ver tabla de References"):
            st.dataframe(
                resultado.resumen_referencias,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Fix Cost":         st.column_config.NumberColumn(format="$%.2f"),
                    "Total Amount":     st.column_config.NumberColumn(format="$%.2f"),
                    "Peso Total (Kgs)": st.column_config.NumberColumn(format="%.2f"),
                },
            )

        # ───────────────────────────────────────────────────
        # 🔄 SECCIÓN DE AUDITORÍA: Items reasignados a Miscelaneus
        # 🔧 FIX: Todo este bloque ahora está CORRECTAMENTE indentado
        #         dentro del if (antes estaba fuera del if).
        # ───────────────────────────────────────────────────
        reporte_misc = getattr(resultado, "reporte_miscelaneus", None) or {}
        items_reasignados = reporte_misc.get("items_reasignados", 0)

        if items_reasignados > 0:
            st.subheader("🔄 Regla Miscelaneus aplicada")

            # Métricas (usando variables NUEVAS, no reusar c1, c2, c3)
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

            # Tabla de detalle
            with st.expander("🔍 Ver items reasignados a Miscelaneus"):
                df_detalle = reporte_misc.get("detalle")

                if df_detalle is not None and len(df_detalle) > 0:
                    # 🔧 FIX: Detectar columnas dinámicamente
                    # (acepta nombres lógicos 'Item' o legacy 'No. Parte Prov.')
                    columnas_preferidas = [
                        "Reference",
                        "Item",                  # nombre lógico nuevo
                        "No. Parte Prov.",       # nombre legacy
                        "BU",
                        "BU Final",
                        "Peso Bruto",            # nombre lógico nuevo
                        "Peso Bruto (Kgs)",      # nombre legacy
                        "Amount",
                    ]
                    columnas_mostrar = [
                        c for c in columnas_preferidas
                        if c in df_detalle.columns
                    ]

                    # Si no se encontraron las preferidas, mostrar todo
                    if not columnas_mostrar:
                        columnas_mostrar = list(df_detalle.columns)

                    st.dataframe(
                        df_detalle[columnas_mostrar],
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "Amount": st.column_config.NumberColumn(format="$%.2f"),
                            "Peso Bruto": st.column_config.NumberColumn(format="%.2f"),
                            "Peso Bruto (Kgs)": st.column_config.NumberColumn(format="%.2f"),
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
        with st.expander(f"🔍 Ver detalle ({len(resultado.detalle):,} filas)"):
            st.dataframe(
                resultado.detalle,
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
        buffer = generar_excel_solo_land(
            resultado,
            st.session_state[Estado.COSTO_LAND],
        )
        st.download_button(
            "📥 Descargar Land.xlsx",
            data=buffer,
            file_name=f"Land_{datetime.now():%Y%m%d_%H%M}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )