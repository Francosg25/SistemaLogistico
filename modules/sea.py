import pandas as pd
import numpy as np
import logging
from typing import Dict, List, Union

logger = logging.getLogger(__name__)

def procesar_sea(
    df_sea: pd.DataFrame, 
    contenedores_capex: List[Union[str, dict]], 
    costo_fijo: float = 2500.0
) -> Dict[str, pd.DataFrame]:
    """
    Procesa las importaciones marítimas distribuyendo el costo por contenedor.
    Aplica la regla crítica CAPEX, donde dichos ítems absorben todo el costo.
    """
    try:
        logger.info("Iniciando procesamiento de módulo SEA...")
        df = df_sea.copy()
        
        # 1. Validación de esquema base
        columnas_req = ['BU', 'Item Code', 'Container Number', 'Total Gross Weight']
        faltantes = [c for c in columnas_req if c not in df.columns]
        if faltantes:
            raise ValueError(f"Columnas faltantes en df_sea: {faltantes}")

        df['Total Gross Weight'] = pd.to_numeric(df['Total Gross Weight'], errors='coerce').fillna(0.0)

        # 2. Inyección Dinámica de Registros CAPEX
        # Generamos los registros que no vienen en el reporte fuente
        if contenedores_capex:
            filas_capex = []
            for item in contenedores_capex:
                if isinstance(item, str):
                    # Inyección básica si solo se pasa el número de contenedor
                    filas_capex.append({'Container Number': item, 'Item Code': 'CAPEX-MANUAL', 'BU': 'Capex', 'Total Gross Weight': 0.0})
                elif isinstance(item, dict):
                    # Inyección detallada (esperada)
                    filas_capex.append({
                        'Container Number': item.get('Container Number'),
                        'Item Code': item.get('Item Code', 'CAPEX-MANUAL'),
                        'BU': 'Capex',
                        'Total Gross Weight': 0.0
                    })
            df_inyectado = pd.DataFrame(filas_capex)
            df = pd.concat([df, df_inyectado], ignore_index=True)

        # 3. Identificación de lógica CAPEX
        df['Item Code'] = df['Item Code'].fillna('').astype(str)
        df['is_capex_item'] = df['Item Code'].str.upper().str.contains('CAPEX')

        # Forzamos las reglas de negocio en los ítems CAPEX detectados o inyectados
        df.loc[df['is_capex_item'], 'BU'] = 'Capex'
        df.loc[df['is_capex_item'], 'Total Gross Weight'] = 0.0

        # Identificamos QUÉ contenedores están "contaminados" por un ítem CAPEX
        contenedores_con_capex = df[df['is_capex_item']]['Container Number'].unique()
        df['is_capex_container'] = df['Container Number'].isin(contenedores_con_capex)

        # 4. Cálculo del peso total por contenedor (Agrupación vectorizada)
        totales_cont = df.groupby('Container Number')['Total Gross Weight'].sum().reset_index()
        totales_cont.rename(columns={'Total Gross Weight': 'Container_Total_Weight'}, inplace=True)
        df = df.merge(totales_cont, on='Container Number', how='left')

        # 5. Motor de Reglas y Cálculo de %Pond / Cost
        # Lógica anidada: 
        # A) ¿Es contenedor CAPEX? -> Sí: ¿Es el ítem CAPEX? -> 100%, sino 0%
        # B) ¿No es contenedor CAPEX? -> Proporción estándar
        
        proporcion_normal = np.where(
            df['Container_Total_Weight'] > 0,
            df['Total Gross Weight'] / df['Container_Total_Weight'],
            0.0
        )

        df['%Pond'] = np.where(
            df['is_capex_container'],
            np.where(df['is_capex_item'], 1.0, 0.0),  # El ítem CAPEX absorbe todo
            proporcion_normal                         # Regla estándar
        )

        df['Cost'] = df['%Pond'] * costo_fijo

        # 6. Generación de entregables secundarios
        # Resumen BU
        resumen_bu = df.groupby('BU')['Cost'].sum().reset_index()
        resumen_bu.rename(columns={'Cost': 'Amount(USD)'}, inplace=True)
        
        total_global_sea = resumen_bu['Amount(USD)'].sum()
        resumen_bu['%PCT'] = np.where(
            total_global_sea > 0, 
            resumen_bu['Amount(USD)'] / total_global_sea, 
            0.0
        )

        # Maestro de Contenedores
        contenedores = df[['Container Number']].drop_duplicates().reset_index(drop=True)
        contenedores['Costo Fijo'] = costo_fijo

        # 7. Limpieza de memoria (Clean Code)
        df.drop(columns=['is_capex_item', 'is_capex_container', 'Container_Total_Weight'], inplace=True)

        logger.info("Módulo SEA procesado exitosamente.")
        return {
            "detalle": df,
            "resumen_bu": resumen_bu,
            "contenedores": contenedores
        }

    except Exception as e:
        logger.error(f"Error crítico en procesar_sea: {str(e)}")
        raise