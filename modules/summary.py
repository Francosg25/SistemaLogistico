import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

def _normalizar_resumen(df: pd.DataFrame, col_bu: str, col_monto: str, nombre_flujo: str) -> pd.DataFrame:
    """Extrae y estandariza los montos absolutos de cualquier módulo."""
    if df is None or df.empty:
        return pd.DataFrame(columns=['BU', 'Amount', 'Flujo'])
    
    df_norm = df[[col_bu, col_monto]].copy()
    df_norm.columns = ['BU', 'Amount']
    df_norm['Flujo'] = nombre_flujo
    df_norm['BU'] = df_norm['BU'].astype(str).str.strip().str.upper()
    return df_norm

def generar_summary(resultado_outbound: dict, resultado_sea: dict, resultado_land: dict) -> pd.DataFrame:
    """
    Consolida los costos logísticos en una tabla pivote dinámica por BU.
    Aplica exclusión estricta de CAPEX y MCS para los porcentajes marítimos.
    """
    try:
        logger.info("Iniciando generación de Summary Consolidado...")

        # 1. Extracción y Normalización
        df_out = _normalizar_resumen(
            resultado_outbound.get('resumen_bu'), 'BU_Inferred', 'Log.Exp', 'Outbound'
        )
        df_sea = _normalizar_resumen(
            resultado_sea.get('resumen_bu'), 'BU', 'Amount(USD)', 'Sea'
        )
        df_land = _normalizar_resumen(
            resultado_land.get('resumen_bu'), 'BU', 'Monto Total', 'Land'
        )

        # Unimos todo en un formato transaccional (Long format)
        df_master = pd.concat([df_out, df_sea, df_land], ignore_index=True)
        
        if df_master.empty:
            logger.warning("No hay datos para generar el summary.")
            return pd.DataFrame()

        # Consolidar montos por si hay BUs duplicados en el mismo flujo
        df_master = df_master.groupby(['Flujo', 'BU'])['Amount'].sum().reset_index()

        # 2. Generación de Tabla de Montos Absolutos ($)
        pivot_usd = df_master.pivot_table(
            index='Flujo', columns='BU', values='Amount', aggfunc='sum', fill_value=0.0
        )
        
        # Añadir columna de Total Absoluto
        pivot_usd.insert(0, 'Total $', pivot_usd.sum(axis=1))
        
        # Renombrar índice para claridad
        pivot_usd.index = [f"{idx} $" for idx in pivot_usd.index]

        # 3. Generación de Tabla de Porcentajes (%PCT)
        # Copiamos el dataframe transaccional para calcular porcentajes de forma segura
        df_pct = df_master.copy()
        
        # Inicializamos columna PCT
        df_pct['PCT'] = 0.0

        for flujo in ['Outbound', 'Land', 'Sea']:
            mask_flujo = df_pct['Flujo'] == flujo
            
            if flujo == 'Sea':
                # REGLA CRÍTICA: Excluir CAPEX y MCS del denominador
                mask_exclusiones = df_pct['BU'].isin(['CAPEX', 'MCS'])
                mask_validos_sea = mask_flujo & ~mask_exclusiones
                
                # El denominador es la suma del Sea excluyendo esos BUs
                subtotal_sea = df_pct.loc[mask_validos_sea, 'Amount'].sum()
                
                # Asignamos porcentaje solo a los BUs válidos. CAPEX/MCS quedan en 0%
                df_pct.loc[mask_validos_sea, 'PCT'] = np.where(
                    subtotal_sea > 0,
                    df_pct.loc[mask_validos_sea, 'Amount'] / subtotal_sea,
                    0.0
                )
            else:
                # Regla estándar para Land y Outbound
                total_flujo = df_pct.loc[mask_flujo, 'Amount'].sum()
                df_pct.loc[mask_flujo, 'PCT'] = np.where(
                    total_flujo > 0,
                    df_pct.loc[mask_flujo, 'Amount'] / total_flujo,
                    0.0
                )

        # Pivoteamos la tabla de porcentajes
        pivot_pct = df_pct.pivot_table(
            index='Flujo', columns='BU', values='PCT', aggfunc='sum', fill_value=0.0
        )
        
        # Alineamos las columnas con la tabla de USD (insertamos Total $ como vacío o NaN para alinear)
        pivot_pct.insert(0, 'Total $', np.nan)
        pivot_pct.index = [f"{idx} %PCT" for idx in pivot_pct.index]

        # 4. Consolidación Final
        # Forzamos el orden de las filas según el requerimiento
        orden_filas = ['Sea %PCT', 'Land %PCT', 'Outbound %PCT', 'Sea $', 'Land $', 'Outbound $']
        
        df_summary = pd.concat([pivot_pct, pivot_usd])
        
        # Reordenamos ignorando los índices que no existan (por si un flujo vino vacío)
        df_summary = df_summary.reindex([f for f in orden_filas if f in df_summary.index])

        logger.info("Summary consolidado exitosamente.")
        return df_summary

    except Exception as e:
        logger.error(f"Error crítico consolidando summary: {e}")
        raise