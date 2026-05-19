"""
═══════════════════════════════════════════════════════════════
VALIDADOR CRÍTICO — Bloqueo de exportación si hay errores
═══════════════════════════════════════════════════════════════
Resuelve el bug arquitectónico: la exportación NO debe permitirse
si hay ERROR/CRITICAL. Antes era opt-in; ahora es opt-out.
═══════════════════════════════════════════════════════════════
"""
from typing import List, Tuple
from dataclasses import dataclass

from src.utils.config_loader import get_config


@dataclass
class DecisionExport:
    permitir: bool
    razones_bloqueo: List[str]
    advertencias: List[str]


def evaluar_exportacion(reporte_validacion) -> DecisionExport:
    """
    Decide si se permite exportar el Excel basándose en el reporte.

    Reglas:
      - Si hay CRITICAL → BLOQUEA siempre
      - Si hay ERROR y config.bloquear_export_si_error → BLOQUEA
      - Si hay WARNING → permite con advertencia
      - Si reporte está vacío → BLOQUEA (no se ejecutó nada)
    """
    config = get_config()
    bloquear_si_error = config.get("validaciones.bloquear_export_si_error", True)

    razones: List[str] = []
    advs: List[str] = []

    if reporte_validacion is None:
        return DecisionExport(
            permitir=False,
            razones_bloqueo=["❌ No se ejecutaron validaciones"],
            advertencias=[],
        )

    if reporte_validacion.total == 0:
        return DecisionExport(
            permitir=False,
            razones_bloqueo=["❌ Reporte de validación vacío"],
            advertencias=[],
        )

    # Cuenta por severidad
    from src.validaciones.reporte_validacion import Severidad
    criticos = reporte_validacion.por_severidad(Severidad.CRITICAL)
    errores = reporte_validacion.por_severidad(Severidad.ERROR)
    warnings = reporte_validacion.por_severidad(Severidad.WARNING)

    if criticos:
        razones.append(f"🚨 {len(criticos)} validación(es) CRÍTICAS sin resolver")
        for h in criticos[:3]:
            razones.append(f"   • [{h.operacion}] {h.regla}: {h.mensaje}")

    if errores and bloquear_si_error:
        razones.append(f"🔴 {len(errores)} ERROR(es) detectados")
        for h in errores[:3]:
            razones.append(f"   • [{h.operacion}] {h.regla}: {h.mensaje}")

    if warnings:
        advs.append(f"🟡 {len(warnings)} advertencia(s) — revisar antes de exportar")

    return DecisionExport(
        permitir=(len(razones) == 0),
        razones_bloqueo=razones,
        advertencias=advs,
    )