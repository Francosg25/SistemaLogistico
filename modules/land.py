import pandas as pd
import numpy as np
import logging
from typing import Dict

logger = logging.getLogger(__name__)

def procesar_land(df_land: pd.DataFrame, costo_fijo: float = 1200.0) -> Dict[str, pd.DataFrame]:
    """
    Procesa las importaciones terrestres distribuyendo un costo fijo por Referencia.
    Confía en el BU reportado en origen, con normalización preventiva.
    """
    try:
        logger.info("Iniciando procesamiento de módulo LAND...")
        df = df_land.copy()

        # 1. Validación de esquema
        columnas_req = ['Reference', 'BU', 'Peso Bruto (Kgs)']
        faltantes = [c for c in columnas_req if c not in df.columns]
        if faltantes:
            raise ValueError(f"Columnas faltantes en df_land: {faltantes}")

        # 2. Limpieza y Normalización
        # Asegurar tipos numéricos y prevenir división por nulos
        df['Peso Bruto (Kgs)'] = pd.to_numeric(df['Peso Bruto (Kgs)'], errors='coerce').fillna(0.0)
        
        # Normalizar BU para evitar duplicados en la agrupación por espacios o casing
        df['BU'] = df['BU'].astype(str).str.strip().str.upper()

        # 3. Cálculo de Pesos Totales por Referencia
        totales_ref = df.groupby('Reference')['Peso Bruto (Kgs)'].sum().reset_index()
        totales_ref.rename(columns={'Peso Bruto (Kgs)': 'Total_Reference_Weight'}, inplace=True)
        
        # Unir totales al DataFrame principal
        df = df.merge(totales_ref, on='Reference', how='left')

        # 4. Motor de Prorrateo (Vectorizado)
        # Si la referencia tiene 0 peso total (ej. datos faltantes en origen),
        # evitamos ZeroDivisionError. Los ítems sin peso reportado tendrán costo 0.
        # En sistemas de producción estrictos, podríamos aplicar un fallback equitativo (1/N).
        df['%Pond'] = np.where(
            df['Total_Reference_Weight'] > 0,
            df['Peso Bruto (Kgs)'] / df['Total_Reference_Weight'],
            0.0
        )

        # Cálculo del costo final distribuido
        df['Cost'] = df['%Pond'] * costo_fijo

        # 5. Generación de Entregables
        
        # A. Resumen por Business Unit
        resumen_bu = df.groupby('BU')['Cost'].sum().reset_index()
        resumen_bu.rename(columns={'Cost': 'Monto Total'}, inplace=True)
        
        monto_global = resumen_bu['Monto Total'].sum()
        resumen_bu['%'] = np.where(
            monto_global > 0,
            resumen_bu['Monto Total'] / monto_global,
            0.0
        )

        # B. Resumen de Auditoría por Referencias (Agregación múltiple)
        resumen_referencias = df.groupby('Reference').agg(
            Items=('Reference', 'count'),
            Peso_Total=('Peso Bruto (Kgs)', 'sum'),
            Costo_Total=('Cost', 'sum')
        ).reset_index()

        # Limpieza de memoria (Clean Code)
        df.drop(columns=['Total_Reference_Weight'], inplace=True)

        logger.info("Módulo LAND procesado exitosamente.")
        return {
            "detalle": df,
            "resumen_bu": resumen_bu,
            "resumen_referencias": resumen_referencias
        }

    except Exception as e:
        logger.error(f"Error crítico en procesar_land: {str(e)}")
        raise