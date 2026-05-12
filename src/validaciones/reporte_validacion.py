"""
Estructuras de datos para el reporte de validación.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum
from datetime import datetime


class Severidad(str, Enum):
    """Niveles de severidad de un hallazgo de validación."""
    OK = "OK"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
    
    @property
    def emoji(self) -> str:
        return {
            "OK":       "🟢",
            "INFO":     "ℹ️",
            "WARNING":  "🟡",
            "ERROR":    "🔴",
            "CRITICAL": "🚨",
        }[self.value]
    
    @property
    def color(self) -> str:
        """Color para usar en la UI de Streamlit."""
        return {
            "OK":       "green",
            "INFO":     "blue",
            "WARNING":  "orange",
            "ERROR":    "red",
            "CRITICAL": "red",
        }[self.value]


@dataclass
class Hallazgo:
    """Un hallazgo individual de validación."""
    regla: str                              # Nombre de la regla validada
    severidad: Severidad                    # Nivel de severidad
    mensaje: str                            # Mensaje legible
    operacion: str = "general"              # 'sea', 'land', 'outbound', 'summary', 'general'
    valor_esperado: Optional[any] = None    # Lo que debería ser
    valor_obtenido: Optional[any] = None    # Lo que es realmente
    detalle: Optional[str] = None           # Información adicional
    accion_sugerida: Optional[str] = None   # Qué hacer al respecto
    
    def to_dict(self) -> Dict:
        return {
            "regla": self.regla,
            "severidad": self.severidad.value,
            "emoji": self.severidad.emoji,
            "operacion": self.operacion,
            "mensaje": self.mensaje,
            "valor_esperado": self.valor_esperado,
            "valor_obtenido": self.valor_obtenido,
            "detalle": self.detalle,
            "accion_sugerida": self.accion_sugerida,
        }


@dataclass
class ReporteValidacion:
    """Reporte consolidado de todas las validaciones ejecutadas."""
    hallazgos: List[Hallazgo] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # ─────────────────────────────────────────────────────────
    # PROPIEDADES DE CONVENIENCIA
    # ─────────────────────────────────────────────────────────
    @property
    def total(self) -> int:
        return len(self.hallazgos)
    
    @property
    def total_ok(self) -> int:
        return sum(1 for h in self.hallazgos if h.severidad == Severidad.OK)
    
    @property
    def total_warnings(self) -> int:
        return sum(1 for h in self.hallazgos if h.severidad == Severidad.WARNING)
    
    @property
    def total_errores(self) -> int:
        return sum(
            1 for h in self.hallazgos 
            if h.severidad in (Severidad.ERROR, Severidad.CRITICAL)
        )
    
    @property
    def estado_global(self) -> Severidad:
        """Determina el estado general del reporte."""
        if any(h.severidad == Severidad.CRITICAL for h in self.hallazgos):
            return Severidad.CRITICAL
        if any(h.severidad == Severidad.ERROR for h in self.hallazgos):
            return Severidad.ERROR
        if any(h.severidad == Severidad.WARNING for h in self.hallazgos):
            return Severidad.WARNING
        return Severidad.OK
    
    @property
    def puede_exportar(self) -> bool:
        """¿Es seguro generar el Excel de salida?"""
        return self.estado_global not in (Severidad.CRITICAL, Severidad.ERROR)
    
    # ─────────────────────────────────────────────────────────
    # MÉTODOS
    # ─────────────────────────────────────────────────────────
    def agregar(self, hallazgo: Hallazgo) -> None:
        self.hallazgos.append(hallazgo)
    
    def por_operacion(self, operacion: str) -> List[Hallazgo]:
        return [h for h in self.hallazgos if h.operacion == operacion]
    
    def por_severidad(self, severidad: Severidad) -> List[Hallazgo]:
        return [h for h in self.hallazgos if h.severidad == severidad]
    
    def resumen(self) -> Dict[str, any]:
        return {
            "timestamp": self.timestamp,
            "estado_global": self.estado_global.value,
            "emoji_global": self.estado_global.emoji,
            "puede_exportar": self.puede_exportar,
            "total_validaciones": self.total,
            "ok": self.total_ok,
            "warnings": self.total_warnings,
            "errores": self.total_errores,
        }