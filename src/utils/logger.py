"""
Sistema de logging centralizado con rotación de archivos
y salida con colores en consola.
"""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import colorlog
from src.utils.config_loader import get_config


def configurar_logger(nombre: str = "consolidacion") -> logging.Logger:
    """
    Configura un logger con:
    - Salida a archivo con rotación
    - Salida a consola con colores
    """
    config = get_config()
    nivel = config.get("logging.nivel", "INFO")
    archivo = config.get("logging.archivo", "./logs/app.log")
    formato = config.get("logging.formato")
    rotacion_mb = config.get("logging.rotacion_mb", 10)
    backup_count = config.get("logging.backup_count", 5)
    
    # Crear directorio de logs si no existe
    Path(archivo).parent.mkdir(parents=True, exist_ok=True)
    
    logger = logging.getLogger(nombre)
    logger.setLevel(nivel)
    
    if logger.handlers:  # Evitar duplicados
        return logger
    
    # === Handler de archivo (rotación) ===
    file_handler = RotatingFileHandler(
        archivo,
        maxBytes=rotacion_mb * 1024 * 1024,
        backupCount=backup_count,
        encoding="utf-8"
    )
    file_handler.setFormatter(logging.Formatter(formato))
    logger.addHandler(file_handler)
    
    # === Handler de consola (con colores) ===
    console_handler = colorlog.StreamHandler()
    console_handler.setFormatter(
        colorlog.ColoredFormatter(
            "%(log_color)s" + formato,
            log_colors={
                "DEBUG": "cyan",
                "INFO": "green",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "red,bg_white",
            }
        )
    )
    logger.addHandler(console_handler)
    
    return logger
