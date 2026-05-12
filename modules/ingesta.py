import pandas as pd
import logging
from typing import Dict, List
from pathlib import Path

# Configuración de logging para auditoría (Bloque 1)
logger = logging.getLogger(__name__)

class IngestionError(Exception):
    """Excepción personalizada para errores críticos de carga."""
    pass

def limpiar_dataframe(df: pd.DataFrame, columnas_requeridas: List[str]) -> pd.DataFrame:
    """Limpia espacios, maneja nulos en columnas clave y normaliza tipos."""
    # 1. Eliminar filas totalmente vacías
    df = df.dropna(how='all')
    
    # 2. Limpiar nombres de columnas (quitar espacios y saltos de línea)
    df.columns = [str(c).strip().replace('\n', ' ') for c in df.columns]
    
    # 3. Validar presencia de columnas
    missing = [col for col in columnas_requeridas if col not in df.columns]
    if missing:
        raise IngestionError(f"Faltan columnas obligatorias: {missing}")
    
    # 4. Limpieza de datos: Stripping a strings y reemplazo de NaN en numéricos
    for col in df.columns:
        if df[col].dtype == 'object':
            df[col] = df[col].astype(str).str.strip()
    
    return df[columnas_requeridas]

def cargar_datos(ruta_archivo: str) -> Dict[str, pd.DataFrame]:
    """
    Lee y procesa las 3 hojas principales del archivo logístico.
    Retorna un diccionario con DataFrames normalizados.
    """
    path = Path(ruta_archivo)
    if not path.exists():
        raise FileNotFoundError(f"No se encontró el archivo en: {ruta_archivo}")

    try:
        # Cargamos el archivo completo una sola vez para eficiencia
        excel_file = pd.ExcelFile(ruta_archivo)
        
        # --- CONFIGURACIÓN DE LAS HOJAS (Mapeo basado en requerimientos) ---
        config_hojas = {
            "Outbound": {
                "skiprows": 7, # Fila 8 (índice 7 en pandas)
                "cols": ["Inbound/Outbound", "Method", "Reference", "BU", "Gross Weight", 
                         "Waybill Number", "Customer", "ADDRESS", "Item", "Qty Pzas"]
            },
            "Sea": {
                "skiprows": 4, # Fila 5 (índice 4)
                "cols": ["BU", "Item Code", "Container Number", "Total Gross Weight"]
            },
            "Land": {
                "skiprows": 4, # Fila 5 (índice 4)
                "cols": ["Inbound/Outbound", "Method", "Reference", "BU", "Peso Bruto (Kgs)", "No. Parte Prov."]
            }
        }

        resultados = {}

        for nombre_hoja, params in config_hojas.items():
            if nombre_hoja not in excel_file.sheet_names:
                logger.warning(f"Hoja '{nombre_hoja}' no encontrada. Saltando...")
                resultados[nombre_hoja.lower()] = pd.DataFrame(columns=params["cols"])
                continue

            # Lectura
            df_raw = pd.read_excel(
                excel_file, 
                sheet_name=nombre_hoja, 
                skiprows=params["skiprows"]
            )
            
            # Limpieza y Validación
            df_limpio = limpiar_dataframe(df_raw, params["cols"])
            
            # Normalización de tipos numéricos (ej. pesos y cantidades)
            # Buscamos columnas con 'Peso', 'Gross', 'Qty', 'Total' para asegurar float
            for col in df_limpio.columns:
                if any(k in col for k in ["Weight", "Peso", "Qty", "Total"]):
                    df_limpio[col] = pd.to_numeric(df_limpio[col], errors='coerce').fillna(0.0)

            resultados[f"df_{nombre_hoja.lower()}"] = df_limpio
            logger.info(f"Hoja {nombre_hoja} cargada exitosamente: {len(df_limpio)} filas.")

        return resultados

    except Exception as e:
        logger.error(f"Error crítico en la ingesta: {str(e)}")
        raise IngestionError(f"Fallo al procesar Excel: {e}")