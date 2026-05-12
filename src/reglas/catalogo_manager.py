"""
Gestor del catálogo histórico de Business Units.

Persiste el conocimiento del sistema sobre qué BUs existen, cuándo aparecieron
y qué reglas especiales aplican a cada uno.
"""
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Set
from functools import lru_cache

from src.utils.logger import configurar_logger

logger = configurar_logger("catalogo_manager")


# Ruta default del catálogo
RUTA_CATALOGO_DEFAULT = Path("src/reglas/bu_catalog.json")


class CatalogoManager:
    """
    Gestiona el catálogo histórico de BUs.
    
    Permite:
    - Cargar BUs conocidos
    - Registrar nuevos BUs validados por el usuario
    - Mantener historial de cambios
    - Consultar reglas especiales por BU
    """
    
    def __init__(self, ruta: Path = RUTA_CATALOGO_DEFAULT):
        self.ruta = Path(ruta)
        self._catalogo: Dict = {}
        self._cargar()
    
    # ─────────────────────────────────────────────────────────
    # CARGA Y PERSISTENCIA
    # ─────────────────────────────────────────────────────────
    def _cargar(self) -> None:
        """Carga el catálogo desde el archivo JSON."""
        if not self.ruta.exists():
            logger.warning(f"Catálogo no existe en {self.ruta}. Creando uno vacío.")
            self._catalogo = self._catalogo_vacio()
            self._guardar()
            return
        
        try:
            with open(self.ruta, "r", encoding="utf-8") as f:
                self._catalogo = json.load(f)
            logger.info(f"📚 Catálogo cargado: {len(self._catalogo.get('bus_conocidos', {}))} BUs")
        except Exception as e:
            logger.error(f"Error cargando catálogo: {e}. Usando vacío.")
            self._catalogo = self._catalogo_vacio()
    
    def _guardar(self) -> None:
        """Persiste el catálogo a disco."""
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self._catalogo["ultima_actualizacion"] = datetime.now().isoformat()
        
        with open(self.ruta, "w", encoding="utf-8") as f:
            json.dump(self._catalogo, f, indent=2, ensure_ascii=False)
        logger.info(f"💾 Catálogo guardado en {self.ruta}")
    
    @staticmethod
    def _catalogo_vacio() -> Dict:
        """Estructura vacía del catálogo."""
        return {
            "version": "1.0.0",
            "ultima_actualizacion": datetime.now().isoformat(),
            "bus_conocidos": {},
            "historial_cambios": [],
        }
    
    # ─────────────────────────────────────────────────────────
    # CONSULTAS
    # ─────────────────────────────────────────────────────────
    @property
    def bus_conocidos(self) -> Set[str]:
        """Set de todos los BUs conocidos."""
        return set(self._catalogo.get("bus_conocidos", {}).keys())
    
    @property
    def bus_estandar(self) -> Set[str]:
        """Set de BUs marcados como estándar (M01, M19, etc.)."""
        return {
            bu for bu, info in self._catalogo.get("bus_conocidos", {}).items()
            if info.get("es_estandar", False)
        }
    
    @property
    def bus_especiales(self) -> Set[str]:
        """Set de BUs especiales (Capex, MCS, Machine, Miscelaneus)."""
        return {
            bu for bu, info in self._catalogo.get("bus_conocidos", {}).items()
            if info.get("es_especial", False)
        }
    
    @property
    def bus_excluidos_pct(self) -> Set[str]:
        """BUs que se EXCLUYEN del cálculo de %PCT en el Summary."""
        return {
            bu for bu, info in self._catalogo.get("bus_conocidos", {}).items()
            if not info.get("incluir_en_summary_pct", True)
        }
    
    def info_bu(self, bu: str) -> Optional[Dict]:
        """Retorna toda la información disponible de un BU."""
        return self._catalogo.get("bus_conocidos", {}).get(bu)
    
    def es_conocido(self, bu: str) -> bool:
        """¿El BU está en el catálogo?"""
        return bu in self.bus_conocidos
    
    # ─────────────────────────────────────────────────────────
    # MODIFICACIONES
    # ─────────────────────────────────────────────────────────
    def registrar_bu(
        self,
        bu: str,
        operacion: str,
        descripcion: str = "",
        es_estandar: bool = False,
        es_especial: bool = False,
        incluir_en_summary_pct: bool = True,
    ) -> None:
        """
        Registra un nuevo BU en el catálogo o actualiza uno existente.
        
        Args:
            bu: Código del BU (ej: 'M47', 'NuevaBU')
            operacion: 'sea', 'land' u 'outbound'
            descripcion: Descripción legible del BU
            es_estandar: True si sigue el patrón Mxx
            es_especial: True si es Capex, MCS, Machine, etc.
            incluir_en_summary_pct: False para Capex/MCS
        """
        ahora = datetime.now().isoformat()
        
        if bu in self._catalogo.get("bus_conocidos", {}):
            # Actualización: solo registrar nueva aparición
            info = self._catalogo["bus_conocidos"][bu]
            info["ultima_aparicion"] = ahora
            if operacion not in info.get("operaciones", []):
                info.setdefault("operaciones", []).append(operacion)
            logger.info(f"♻️  BU '{bu}' actualizado en catálogo")
        else:
            # Nuevo BU
            self._catalogo.setdefault("bus_conocidos", {})[bu] = {
                "descripcion": descripcion or f"Business Unit {bu}",
                "primera_aparicion": ahora,
                "ultima_aparicion": ahora,
                "operaciones": [operacion],
                "es_estandar": es_estandar,
                "es_especial": es_especial,
                "incluir_en_summary_pct": incluir_en_summary_pct,
            }
            
            # Registrar en historial
            self._catalogo.setdefault("historial_cambios", []).append({
                "fecha": ahora,
                "tipo": "alta",
                "bu": bu,
                "operacion": operacion,
            })
            logger.info(f"✨ Nuevo BU '{bu}' registrado en catálogo")
        
        self._guardar()
    
    def registrar_aparicion(self, bu: str, operacion: str) -> None:
        """Solo actualiza la fecha de última aparición (sin alta nueva)."""
        if bu in self._catalogo.get("bus_conocidos", {}):
            self._catalogo["bus_conocidos"][bu]["ultima_aparicion"] = datetime.now().isoformat()
            self._guardar()


# ============================================================
# SINGLETON GLOBAL
# ============================================================
@lru_cache(maxsize=1)
def obtener_catalogo() -> CatalogoManager:
    """Retorna la instancia global del catálogo (singleton)."""
    return CatalogoManager()