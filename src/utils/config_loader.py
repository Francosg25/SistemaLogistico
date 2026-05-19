"""
═══════════════════════════════════════════════════════════════
CONFIG LOADER — Singleton con validación + hot-reload + fallback
═══════════════════════════════════════════════════════════════
Arregla los 5 bugs detectados en la auditoría:
  ✅ Validación de schema (no retorna {} en silencio)
  ✅ Hot-reload con reload() público
  ✅ Soporta variable de entorno CONFIG_PATH
  ✅ Thread-safe con Lock
  ✅ Log de claves faltantes
═══════════════════════════════════════════════════════════════
"""
import os
import yaml
import logging
import threading
from pathlib import Path
from typing import Any, Dict, Optional
from functools import lru_cache

# Logger interno (no usa src.utils.logger para evitar ciclo)
_log = logging.getLogger("config_loader")

# Ruta por defecto: raíz del proyecto / config / config.yaml
RUTA_BASE = Path(__file__).resolve().parent.parent.parent
RUTA_CONFIG_DEFAULT = RUTA_BASE / "config" / "config.yaml"


class ConfigError(Exception):
    """Excepción raíz para errores de configuración."""
    pass


class ConfigLoader:
    """Singleton con validación, hot-reload y soporte multi-entorno."""

    _instance: Optional["ConfigLoader"] = None
    _lock = threading.Lock()
    _claves_faltantes: set = set()  # log de claves no encontradas

    # ────────────────────────────────────────────────────────
    # SINGLETON THREAD-SAFE
    # ────────────────────────────────────────────────────────
    def __new__(cls, config_path: Optional[str] = None):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._inicializado = False
            return cls._instance

    def __init__(self, config_path: Optional[str] = None):
        if self._inicializado:
            return

        # Prioridad: argumento > variable de entorno > default
        ruta = (
            config_path
            or os.environ.get("CONFIG_PATH")
            or str(RUTA_CONFIG_DEFAULT)
        )
        self._config_path = ruta
        self._config: Dict[str, Any] = {}
        self._cargar(ruta)
        self._inicializado = True

    # ────────────────────────────────────────────────────────
    # CARGA Y VALIDACIÓN
    # ────────────────────────────────────────────────────────
    def _cargar(self, ruta: str) -> None:
        path = Path(ruta)
        if not path.exists():
            raise ConfigError(f"❌ No se encontró {ruta}")

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ConfigError(f"❌ YAML corrupto: {e}")

        if not isinstance(data, dict):
            raise ConfigError(
                f"❌ El YAML debe ser un dict en la raíz, "
                f"se obtuvo {type(data).__name__}"
            )

        self._config = data
        self._validar_schema()
        _log.info(f"✅ Config cargado desde {ruta}")

    def _validar_schema(self) -> None:
        """Valida que existan las secciones críticas."""
        secciones_obligatorias = [
            "costos.sea.valor",
            "costos.land.valor",
            "costos.outbound.valor",
            "validaciones.tolerancia_costo",
        ]
        faltantes = []
        for clave in secciones_obligatorias:
            if self.get(clave, _silent=True) is None:
                faltantes.append(clave)

        if faltantes:
            raise ConfigError(
                f"❌ Faltan secciones obligatorias en config.yaml: {faltantes}"
            )

    # ────────────────────────────────────────────────────────
    # ACCESO A VALORES
    # ────────────────────────────────────────────────────────
    def get(
        self,
        clave: str,
        default: Any = None,
        _silent: bool = False,
    ) -> Any:
        """
        Acceso por notación de punto: get('costos.outbound.valor')

        Args:
            clave: ruta con puntos al valor
            default: valor por defecto si no existe
            _silent: si True, no loguea warning (uso interno)
        """
        partes = clave.split(".")
        valor: Any = self._config
        for parte in partes:
            if isinstance(valor, dict) and parte in valor:
                valor = valor[parte]
            else:
                if not _silent and clave not in self._claves_faltantes:
                    _log.warning(
                        f"⚠️ Clave '{clave}' no encontrada en config.yaml, "
                        f"usando default={default!r}"
                    )
                    self._claves_faltantes.add(clave)
                return default
        return valor

    def get_required(self, clave: str) -> Any:
        """Igual que get(), pero lanza error si falta."""
        valor = self.get(clave, _silent=True)
        if valor is None:
            raise ConfigError(f"❌ Clave OBLIGATORIA '{clave}' no encontrada")
        return valor

    @property
    def todo(self) -> Dict[str, Any]:
        return self._config

    @property
    def ruta(self) -> str:
        return self._config_path

    # ────────────────────────────────────────────────────────
    # HOT-RELOAD
    # ────────────────────────────────────────────────────────
    def reload(self) -> None:
        """Recarga el YAML desde disco (útil para dev/Streamlit)."""
        with self._lock:
            _log.info("🔄 Recargando config.yaml...")
            self._claves_faltantes.clear()
            self._cargar(self._config_path)
            get_config.cache_clear()


@lru_cache(maxsize=1)
def get_config() -> ConfigLoader:
    """Instancia global cacheada."""
    return ConfigLoader()


def recargar_config() -> ConfigLoader:
    """Forzar recarga (úsalo si cambias el YAML en runtime)."""
    cfg = get_config()
    cfg.reload()
    return cfg