import yaml
from pathlib import Path
from typing import Any, Dict
from functools import lru_cache

# Calcula la ruta absoluta al archivo config.yaml basándose en la ubicación de este script
# __file__ está en src/utils/config_loader.py
# .parent.parent.parent sube hasta la raíz del proyecto
RUTA_BASE = Path(__file__).resolve().parent.parent.parent
RUTA_CONFIG_DEFAULT = RUTA_BASE / "config" / "config.yaml"

class ConfigLoader:
    """Singleton para cargar y acceder a la configuración."""
    
    _instance = None
    _config: Dict[str, Any] = {}
    
    # Actualiza el valor por defecto aquí:
    def __new__(cls, config_path: str = str(RUTA_CONFIG_DEFAULT)):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._cargar(config_path)
        return cls._instance
    
    def _cargar(self, config_path: str) -> None:
        """Carga el archivo YAML."""
        ruta = Path(config_path)
        if not ruta.exists():
            raise FileNotFoundError(f"No se encontró {config_path}")
        
        with open(ruta, "r", encoding="utf-8") as f:
            self._config = yaml.safe_load(f)
    
    def get(self, clave: str, default: Any = None) -> Any:
        """
        Obtiene un valor usando notación de punto.
        Ejemplo: config.get('costos.outbound.valor') → 1500
        """
        partes = clave.split(".")
        valor = self._config
        for parte in partes:
            if isinstance(valor, dict) and parte in valor:
                valor = valor[parte]
            else:
                return default
        return valor
    
    @property
    def todo(self) -> Dict[str, Any]:
        """Retorna toda la configuración."""
        return self._config


@lru_cache(maxsize=1)
def get_config() -> ConfigLoader:
    """Función helper para obtener la instancia global."""
    return ConfigLoader()