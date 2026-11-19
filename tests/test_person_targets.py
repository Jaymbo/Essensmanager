# Tests: Auto-Tagesziele nach Gewicht/Geschlecht (app/person_targets.py).

import os
import tempfile

os.environ.setdefault("EM_DB_PATH", tempfile.mktemp(suffix=".db"))

from app.person_targets import auto_targets, bmr_mifflin, effective_targets


def test_bmr_mifflin():
    # Mann 75 kg, 175 cm, 35 J: 10*75 + 6.25*175 - 5*35 + 5 = 1673.75
    assert abs(bmr_mifflin(75, 175, 35, "m") - 1673.75) < 1e-9
    # Frau 65 kg, 165 cm, 35 J: 650 + 1031.25 - 175 - 161 = 1345.25
    assert abs(bmr_mifflin(65, 165, 35, "f") - 1345.25) < 1e-9


def test_auto_targets_scale_with_weight():
    t75 = auto_targets(75.0, 175, 35, "m")
    t100 = auto_targets(100.0, 175, 35, "m")
    # Protein-Spanne skaliert mit Gewicht
    assert t75["protein_g"] == (60.0, 112.5)
    assert t100["protein_g"] == (80.0, 150.0)
    # Energie bei mehr Gewicht/Gewicht höher
    assert t100["energy_kcal"][0] > t75["energy_kcal"][0]


def test_auto_targets_female_adjustments():
    tm = auto_targets(75.0, 175, 35, "m")
    tf = auto_targets(75.0, 175, 35, "f")
    # Eisen: Frau 15, Mann 10
    assert tf["iron_mg"][0] == 15.0 and tm["iron_mg"][0] == 10.0
    # Zink: Frau 7, Mann 10
    assert tf["zinc_mg"][0] == 7.0 and tm["zinc_mg"][0] == 10.0


def test_amino_acids_scaled_by_weight():
    t = auto_targets(70.0, 175, 35, "m")
    # Leucin: 39 mg/kg * 70 = 2.73 g
    assert abs(t["leucine_g"][0] - 2.73) < 1e-9
    assert t["leucine_g"][1] is None


def test_overrides_win_over_auto():
    base = auto_targets(75.0, 175, 35, "m")
    eff = effective_targets(base, {"iron_mg": {"min": 5.0},
                                   "vit_c_mg": {"max": 1000.0},
                                   "fiber_g": {"min": None, "max": 40.0}})
    assert eff["iron_mg"][0] == 5.0
    assert eff["vit_c_mg"][1] == 1000.0
    assert eff["fiber_g"][0] is None and eff["fiber_g"][1] == 40.0
    # Unberührte Keys unverändert
    assert eff["protein_g"] == base["protein_g"]


def test_activity_affects_energy():
    sedentary = auto_targets(75.0, 175, 35, "m", activity=1.2)
    active = auto_targets(75.0, 175, 35, "m", activity=1.8)
    assert active["energy_kcal"][0] > sedentary["energy_kcal"][0]
