"""MILP optimizer — placeholder for the team's model (Orquestador NBA Configurable, J. Reina).

Expected model (see docs/metodologia.md once added):

    max  Σ_{i,p,c} (w_valor · SP_i^p · SC_i^c · VN_p + w_jer · nivel_p + bonus_i^{p,c}) · Z_i^{p,c}
    s.t. Σ_p Z_i^{p,c} ≤ M_c · Z_i^c                       (activation + products per contact, R14)
         Σ_c Z_i^c ≤ min(canales_por_cliente, room_i)      (R13, R15)
         Σ_i Z_i^c ≤ K_c                                   (capacity, R16)
         business constraints from config_restricciones   (linear quotas)
         Z_i^{p,c} = 0 where eligible/channel_ok/allowed is False (masks: R01–R12, never created)
         Z ∈ {0, 1}

Must return SolveResult with ``duals = {"capacity": {c: price}, "business": {id: price}}`` from the
LP relaxation (HiGHS via ``highspy``), and honour ``optimizador.tiempo_max_s`` / ``optimizador.gap``.
TODO(J. Reina): objective weights and the hierarchy treatment are modelling decisions.
"""
from __future__ import annotations

from engine.optimizers.base import SolveInput, SolveResult, register


@register
class MilpOptimizer:
    name = "milp"
    label = "Optimización MILP"
    available = False  # flip to True once solve() is implemented (fase 5)
    supports = {"reglas_duras", "reglas_blandas", "restricciones_negocio", "multicanal", "precios_sombra",
                "jerarquia_estricta"}

    def solve(self, inp: SolveInput) -> SolveResult:
        raise NotImplementedError("El optimizador MILP está en construcción (fase 5).")
