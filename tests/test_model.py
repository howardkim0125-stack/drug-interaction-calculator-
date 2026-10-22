import pytest

import model

TOL = 1e-3


def approx(x):
    return pytest.approx(x, abs=TOL)


def mk(name, metabolism=None, inhibits=None, induces=None, actions=None, dose_ratio=1.0):
    return {"name": name, "dose_ratio": dose_ratio,
            "metabolism": metabolism or {}, "inhibits": inhibits or {},
            "induces": induces or {}, "actions": actions or {}}


def met(f, g=0.0):
    return {"f": f, "g": g, "source": "virtual"}


def inh(s, t=0.0):
    return {"s": s, "t": t, "source": "virtual"}


def test_T1_liver():
    b = mk("B", metabolism={"CYP3A": met(0.7)})
    a = mk("A", inhibits={"CYP3A": inh(0.6)})
    assert model.concentration_ratio(b, [a])["r_liver"] == approx(1.7241)
    assert model.r_from_fractions([(0.7, 1 - 0.6)]) == approx(1.7241)


def test_T2_liver_and_gut():
    b = mk("B", metabolism={"CYP3A": met(0.7, 0.5)})
    a = mk("A", inhibits={"CYP3A": inh(0.6, 0.8)})
    res = model.concentration_ratio(b, [a])
    assert res["r_liver"] == approx(1.7241)
    assert res["r_gut"] == approx(1.6667)
    assert res["r"] == approx(2.8736)


def test_T3_two_inhibitors():
    b = mk("B", metabolism={"CYP3A": met(0.8)})
    others = [mk("A1", inhibits={"CYP3A": inh(0.5)}), mk("A2", inhibits={"CYP3A": inh(0.5)})]
    assert model.concentration_ratio(b, others)["r"] == approx(2.5)


def test_T4_inducer():
    b = mk("B", metabolism={"CYP3A": met(0.5)})
    a = mk("A", induces={"CYP3A": {"u": 1.0, "source": "virtual"}})
    assert model.concentration_ratio(b, [a])["r"] == approx(0.6667)


def test_T5_single_agonist():
    assert model.target_effect([1.0]) == approx(0.5)


def test_T6_c_from_e():
    assert model.c_from_e(0.4) == approx(0.6667)


def test_T7_agonist_with_r():
    c = model.c_from_e(0.4) * 1.7241
    assert model.target_effect([c]) == approx(0.5348)


def test_T8_same_target():
    assert model.target_effect([model.c_from_e(0.3), model.c_from_e(0.4)]) == approx(0.5227)


def test_T8b_same_target_with_r():
    r2 = 1 / (1 - 0.42)
    assert model.target_effect([model.c_from_e(0.3), model.c_from_e(0.4) * r2]) == approx(0.6121)


def test_T9_antagonist():
    assert model.target_effect([1.0], [1.0]) == approx(0.3333)
    assert model.target_effect([3.0], [1.0]) == approx(0.6)
    assert model.target_effect([], [1.0]) == 0


@pytest.mark.parametrize("k,expected", [(0, 0.3333), (1, 0.36), (4, 0.4286), (8, 0.5)])
def test_T10_two_targets(k, expected):
    e = model.e_from_c(0.25)
    assert model.combine([e, e], k) == approx(expected)


def test_T10b_three_targets():
    e = model.e_from_c(0.25)
    assert model.combine_sum([0.25] * 3, 2) == approx(1.1875)
    assert model.combine([e] * 3, 2) == approx(0.5429)


def test_T11_invert():
    roots = sorted(model.inhibition_roots(0.7, 0.5, 2.46305))
    assert roots[0] == approx(0.6)
    assert roots[1] == approx(2.8286)
    assert model.invert_inhibition(0.7, 0.5, 2.46305) == approx(0.6)


def test_T11_invert_gut_zero_and_no_root():
    assert model.invert_inhibition(0.7, 0, 1 / 0.58) == approx(0.6)
    with pytest.raises(ValueError):
        model.invert_inhibition(0.5, 0, 10)
    with pytest.raises(ValueError):
        model.invert_inhibition(0.7, 0.5, 0.8)


def test_T12_ki():
    assert model.s_from_ki(3.0, 3.0) == approx(0.5)


def test_T13_up_and_down():
    up = [model.e_from_c(1.0)]
    down = [model.e_from_c(0.25)]
    assert model.effect_value(up, down, 1) == approx(0.3)


def test_dose_ratio_scales_inhibition_like_concentration():
    # s = 0.5 ↔ x = 1, 용량 2배 → x = 2 → s = 2/3 (Ki 방식으로 농도 2배와 같음)
    assert model.scale_inhibition(0.5, 2) == approx(model.s_from_ki(2.0, 1.0))
    b = mk("B", metabolism={"CYP3A": met(0.6)})
    a = mk("A", inhibits={"CYP3A": inh(0.5)}, dose_ratio=2)
    assert model.concentration_ratio(b, [a])["r"] == approx(1 / (0.6 / 3 + 0.4))


def test_target_actions_uses_r_and_dose_ratio():
    a = mk("A", actions={"P": {"type": "agonist", "c": 0.5, "source": "v"}}, dose_ratio=2)
    b = mk("B", actions={"P": {"type": "antagonist", "c": 1.0, "source": "v"}})
    t = model.target_actions([a, b], {"A": 1.5, "B": 1.0})
    assert t["P"]["E"] == approx(1.5 / (1 + 1.5 + 1.0))


def test_T14_dose_ratio_inhibition():
    assert model.scale_inhibition(0.6, 2) == approx(0.75)


def test_T15_pk_to_c():
    assert model.pk_concentration(0.5, 100, 10, 12) == approx(0.4167)
    assert model.c_from_pk(0.5, 100, 10, 12, 0.41667) == approx(1.0)
