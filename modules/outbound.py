import pandas as pd
import numpy as np
import logging
from typing import Dict

from modules.motor_reglas import ReglasEngine

logger = logging.getLogger(__name__)

def procesar_outbound(df_outbound: pd.DataFrame, costo_fijo: float = 1500.0) -> Dict[str, pd.DataFrame]:
    """
    Procesa las exportaciones calculando proporciones de peso y asignando costos.
    """
    try:
        logger.info("Iniciando procesamiento de módulo Outbound...")
        
        # 1. Copia defensiva y validación de columnas esenciales
        df = df_outbound.copy()
        columnas_requeridas = ['Reference', 'Gross Weight', 'Customer', 'ADDRESS']
        faltantes = [col for col in columnas_requeridas if col not in df.columns]
        if faltantes:
            raise ValueError(f"Faltan columnas requeridas en df_outbound: {faltantes}")

        # 2. Inferencia de BU

        df['BU_Inferred'] = df['Reference'].apply(ReglasEngine.validar_inferencia_outbound)
        # 3. Cálculo de proporciones por Reference
        # Aseguramos que el peso sea numérico
        df['Gross Weight'] = pd.to_numeric(df['Gross Weight'], errors='coerce').fillna(0.0)
        
        # Calculamos el peso total por Referencia y lo unimos al df original
        totales_ref = df.groupby('Reference')['Gross Weight'].sum().reset_index()
        totales_ref.rename(columns={'Gross Weight': 'Total_Reference_Weight'}, inplace=True)
        
        df = df.merge(totales_ref, on='Reference', how='left')

        # Calculamos %Proportion (evitando división por cero)
        df['%Proportion'] = np.where(
            df['Total_Reference_Weight'] > 0, 
            df['Gross Weight'] / df['Total_Reference_Weight'], 
            0.0
        )

        # 4. Cálculo del costo de exportación distribuido
        df['Calc_Exp'] = df['%Proportion'] * costo_fijo

        # 5. Generación de Resumen BU (Separación por BU, Cliente y Dirección)
        resumen_bu = df.groupby(['BU_Inferred', 'Customer', 'ADDRESS'])['Calc_Exp'].sum().reset_index()
        resumen_bu.rename(columns={'Calc_Exp': 'Log.Exp'}, inplace=True)
        
        total_global_exp = resumen_bu['Log.Exp'].sum()
        resumen_bu['%PCT'] = np.where(
            total_global_exp > 0, 
            (resumen_bu['Log.Exp'] / total_global_exp), 
            0.0
        )

        # 6. Generación de maestro de Referencias
        referencias = df[['Reference', 'BU_Inferred']].drop_duplicates().reset_index(drop=True)
        referencias['Fix Cost'] = costo_fijo

        logger.info("Módulo Outbound procesado exitosamente.")

        return {
            "detalle": df,
            "resumen_bu": resumen_bu,
            "referencias": referencias
        }

    except Exception as e:
        logger.error(f"Error crítico en procesar_outbound: {e}")
        raise