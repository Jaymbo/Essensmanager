# Bioverfügbarkeits-Service: verbindet Domain mit DB (Regeln, NutrientDefs).

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .domain import bioavailability as bio
from .domain import nutrient_space as ns
from .models import InteractionRule, NutrientDef


class BodySimulator:
    """Simuliert Resorption + Pools über Tage für eine Person."""

    def __init__(self, session: Session):
        self.s = session
        self.defs: dict[str, NutrientDef] = {
            d.key: d for d in self.s.execute(select(NutrientDef)).scalars().all()
        }
        self.rules = [
            bio.InteractionRule(
                target=r.target, kind=r.kind, compound=r.compound,
                effect=r.effect, half_saturation=r.half_saturation, source=r.source)
            for r in self.s.execute(select(InteractionRule)).scalars().all()
        ]

    def absorb_meal(self, intake_vector: ns.NutrientVector) -> ns.NutrientVector:
        """Mahlzeiten-Vektor (Zufuhr) -> resorbierter Vektor."""
        # Interaktionen wirken auf der Basis der gesamten Mahlzeit:
        meal_compounds = {k: intake_vector.get(k, 0.0) for k in bio.COMPOUND_KEYS}
        out: ns.NutrientVector = {}
        for k, intake in intake_vector.items():
            d = self.defs.get(k)
            eff = d.absorb_efficiency if d else 1.0
            out[k] = bio.absorb(k, intake, eff, self.rules, meal_compounds)
        return out

    def simulate_days(self, daily_intake: list[ns.NutrientVector],
                      pool: bio.PoolState | None = None) -> list[dict]:
        """Für jeden Tag: Resorption, Pool-Update, Status vs. Zielbereich.
        Gibt Liste {day, intake, absorbed, pool, status} zurück."""
        pool = pool or bio.PoolState()
        half_lives = {k: (d.half_life_days if d else None) for k, d in self.defs.items()}
        caps = {k: (d.pool_capacity if d else None) for k, d in self.defs.items()}
        results = []
        for day_i, intake in enumerate(daily_intake):
            absorbed = self.absorb_meal(intake)
            pool_amounts = pool.step(absorbed, half_lives, caps)
            minimum = {k: (d.daily_min or 0.0) for k, d in self.defs.items() if d.daily_min}
            maximum = {k: (d.daily_max or 0.0) for k, d in self.defs.items() if d.daily_max}
            status = ns.diff_status(intake, minimum, maximum)
            results.append({
                "day": day_i,
                "intake": intake,
                "absorbed": absorbed,
                "pool": pool_amounts,
                "status": status,
            })
        return results
