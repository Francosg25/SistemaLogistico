import json
import logging
import re
from pathlib import Path
from typing import Dict, Set, List
import pandas as pd
from datetime import datetime

logger = logging.getLogger(__name__)

# Compilamos la regex a nivel de módulo para que no se re-compile en cada llamada.
# Patrón: Busca el último punto literal '\.', captura el primer bloque alfanumérico, 
# y opcionalmente captura un segundo bloque después de un '/'.
OUTBOUND_BU_PATTERN = re.compile(r'\.([A-Z0-9_]+)(?:/([A-Z0-9_]+))?$', re.IGNORECASE)

class ReglasEngine:
    def __init__(self, catalog_path: str = "config/bu_catalog.json"):
        self.catalog_path = Path(catalog_path)
        self.known_bus: Set[str] = set()
        self._cargar_catalogo()

    def _cargar_catalogo(self):
        """Carga el catálogo histórico de BUs en memoria."""
        if not self.catalog_path.exists():
            logger.warning(f"No se encontró el catálogo en {self.catalog_path}. Se creará uno nuevo.")
            return

        try:
            with open(self.catalog_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.known_bus = set(bu.upper() for bu in data.get("known_bus", []))
            logger.info(f"Catálogo cargado con {len(self.known_bus)} BUs conocidos.")
        except json.JSONDecodeError as e:
            logger.error(f"Catálogo corrupto. Error de lectura JSON: {e}")
            raise

    def detectar_bus_actuales(self, dataframes: Dict[str, pd.DataFrame]) -> Set[str]:
        """
        Escanea dinámicamente los DataFrames en busca de BUs únicos presentes en el mes actual.
        """
        bus_actuales = set()
        
        for name, df in dataframes.items():
            if df is None or df.empty:
                continue
                
            # Determinar la columna correcta según la hoja
            columna_bu = 'BU_Inferred' if 'outbound' in name.lower() else 'BU'
            
            if columna_bu in df.columns:
                # Extraemos, limpiamos espacios y estandarizamos a mayúsculas
                bus_limpios = df[columna_bu].dropna().astype(str).str.strip().str.upper()
                bus_actuales.update(bus_limpios.unique())
                
        # Filtramos artefactos de limpieza (ej. strings vacíos)
        bus_actuales.discard("")
        bus_actuales.discard("SIN_BU")
        bus_actuales.discard("ERROR_BU")
        
        return bus_actuales

    def comparar_con_historico(self, bus_actuales: Set[str]) -> Dict[str, Set[str]]:
        """
        Compara los BUs del mes con el histórico usando teoría de conjuntos (O(1)).
        """
        nuevos = bus_actuales - self.known_bus
        desaparecidos = self.known_bus - bus_actuales
        recurrentes = bus_actuales & self.known_bus

        if nuevos:
            logger.warning(f"¡ALERTA! Se detectaron BUs desconocidos: {nuevos}. Requiere validación manual.")
        if desaparecidos:
            logger.info(f"BUs del catálogo no presentes en este set de datos: {desaparecidos}")

        return {
            "nuevos": nuevos,
            "desaparecidos": desaparecidos,
            "recurrentes": recurrentes
        }

    def actualizar_catalogo(self, bus_validados: Set[str]):
        """Persiste los BUs aprobados en el JSON local para el próximo ciclo."""
        self.known_bus.update(bu.upper() for bu in bus_validados)
        
        estado_actualizado = {
            "version": "1.1",
            "last_updated": datetime.now().isoformat(),
            "known_bus": sorted(list(self.known_bus))
        }
        
        # Aseguramos que el directorio exista antes de guardar
        self.catalog_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.catalog_path, 'w', encoding='utf-8') as f:
            json.dump(estado_actualizado, f, indent=2)
        logger.info("Catálogo de BUs actualizado y persistido en disco.")

    @staticmethod
    def validar_inferencia_outbound(reference: str) -> str:
        """
        Aplica un regex robusto para extraer la unidad de negocio de la referencia.
        Favorece siempre el segundo BU si existe el patrón '/'.
        """
        if pd.isna(reference):
            return "SIN_BU"
            
        ref_str = str(reference).strip()
        match = OUTBOUND_BU_PATTERN.search(ref_str)
        
        if match:
            bu1, bu2 = match.groups()
            # Si existe el grupo 2 (después del '/'), lo retornamos. Si no, retornamos el grupo 1.
            resultado = bu2 if bu2 else bu1
            return resultado.strip().upper()
            
        logger.debug(f"Regex falló para referencia: {ref_str}. Retornando 'SIN_BU'.")
        return "SIN_BU"