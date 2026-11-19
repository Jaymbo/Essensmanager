from app.domain import bioavailability as bio
from app.domain import nutrient_space as ns
from app.domain import processes as proc


def test_add_and_scale():
    a = {"energy_kcal": 100, "vit_c_mg": 10}
    b = {"energy_kcal": 50, "iron_mg": 2}
    s = ns.add(a, b)
    assert s["energy_kcal"] == 150 and s["vit_c_mg"] == 10 and s["iron_mg"] == 2
    assert ns.scale(a, 0.5)["energy_kcal"] == 50


def test_per_100g():
    v = ns.per_100g({"protein_g": 20.0}, 150)
    assert abs(v["protein_g"] - 30.0) < 1e-9
    assert ns.per_100g({"protein_g": 20.0}, 0) == {}


def test_diff_status():
    status = ns.diff_status({"iron_mg": 5}, {"iron_mg": 10}, {"iron_mg": 45})
    assert status["iron_mg"] == "under"
    status = ns.diff_status({"iron_mg": 50}, {"iron_mg": 10}, {"iron_mg": 45})
    assert status["iron_mg"] == "over"
    status = ns.diff_status({"iron_mg": 20}, {"iron_mg": 10}, {"iron_mg": 45})
    assert status["iron_mg"] == "in_range"


def test_process_chain():
    factors = [{"vit_c_mg": 0.5}, {"vit_c_mg": 0.5}]
    out = proc.apply_chain({"vit_c_mg": 100, "protein_g": 10}, factors)
    assert out["vit_c_mg"] == 25.0
    assert out["protein_g"] == 10.0  # unverändert


def test_b12_saturation():
    # Bis 1.5 µg: 50 % Resorption
    assert bio.b12_absorbed(1.0) == 0.5
    # 3 µg: 0.75 aktiv + 0.015 passiv
    assert abs(bio.b12_absorbed(3.0) - 0.765) < 1e-9


def test_interaction_inhibitor():
    rules = [bio.InteractionRule(target="iron_mg", kind="inhibitor",
                                 compound="phytate_g", effect=-0.5,
                                 half_saturation=3, source="test")]
    # Ohne Phytat: Faktor 1
    assert bio.interaction_factor(rules, "iron_mg", {}) == 1.0
    # Mit viel Phytat: bis zu 0.5
    f = bio.interaction_factor(rules, "iron_mg", {"phytate_g": 30})
    assert f < 0.6


def test_pool_decay():
    pool = bio.PoolState({"vit_c_mg": 1000.0})
    out = pool.step({}, {"vit_c_mg": 30}, {})
    # Nach einem Tag mit HWZ 30 Tage: 1000 * 0.5^(1/30) ≈ 977
    assert 970 < out["vit_c_mg"] < 980
