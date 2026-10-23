"""웹앱(docs/core.js)이 파이썬과 같은 결과를 내는지 확인한다. Node가 없으면 건너뛴다."""
import json
import random
import shutil
import subprocess
import warnings
from itertools import combinations

import pytest

import calc_trace
import data_io
import interpret
import web_build
from virtual import generator

ROOT = data_io.ROOT
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js가 없어 웹앱 검사를 건너뜀")

CFG = data_io.load_config()
ENZ = data_io.read_json(data_io.DATA_DIR / "names.json")["enzymes"]


def v(**kw):
    return {**kw, "source": "virtual"}


E2E = {
    "E2E-1": ([{"name": "A", "inhibits": {"CYP3A": v(s=0.6, t=0)}, "actions": {"P": v(type="agonist", e=0.3)}},
               {"name": "B", "metabolism": {"CYP3A": v(f=0.7, g=0)}, "actions": {"P": v(type="agonist", e=0.4)}}],
              {"effects": {"X": v(up=["P"])}}),
    "E2E-2": ([{"name": "A", "actions": {"P": v(type="agonist", c=0.25)}},
               {"name": "B", "actions": {"Q": v(type="agonist", c=0.25)}}],
              {"effects": {"Y": v(up=["P", "Q"], k=4)}}),
    "E2E-3": ([{"name": "A", "inhibits": {"CYP3A": v(s=0.5, t=0)}},
               {"name": "B", "inhibits": {"CYP3A": v(s=0.5, t=0)}},
               {"name": "C", "metabolism": {"CYP3A": v(f=0.8, g=0)}}],
              {"effects": {"X": v(up=["P"])}}),
}

# 입력 방식과 계산 갈래를 골고루 지나가도록 만든 가상 약
SPECIAL_DRUGS = [
    {"name": "K1", "dose_ratio": 2,
     "metabolism": {"CYP2D6": v(f=0.5, g=0)},
     "inhibits": {"CYP3A": v(Ki=1, conc_liver=1, conc_gut=3)},
     "actions": {"P": v(type="agonist", F=0.5, dose=100, CL=10, tau=12, EC50=0.41667)}},
    {"name": "K2", "metabolism": {"CYP3A": v(f=0.6, g=0.4), "CYP2C19": v(f=0.4, g=0)},
     "induces": {"CYP2D6": v(u=0.8)},
     "actions": {"P": v(type="antagonist", F=0.8, dose=50, CL=5, tau=24, KB=0.1), "Q": v(type="agonist", c=2.5)}},
    {"name": "K3", "dose_ratio": 0.5, "metabolism": {"CYP3A": v(f=1.0, g=0.6)},
     "inhibits": {"CYP2C19": v(s=0.9, t=0.94)}, "induces": {"CYP3A": v(u=1.5)},
     "actions": {"R": v(type="agonist", e=0.6), "S": v(type="agonist", c=0.05)}},
    {"name": "가상약가", "metabolism": {"CYP1A2": v(f=0.3, g=0)},
     "actions": {"S": v(type="antagonist", c=3), "Z": v(type="agonist", c=1)}},
]
SPECIAL_RULES = {"effects": {
    "합산": v(up=["P", "Q"], k=0, threshold=0.5),
    "겹침": v(up=["Q", "R", "S"], down=["P"], k=0.4, threshold=0.3),
    "음수": v(up=["T"], down=["R", "S"], k=6),
    "작음": v(up=["S"], threshold=0.02),
}}


def cases():
    out = [{"id": name, "drugs": drugs, "rules": rules} for name, (drugs, rules) in E2E.items()]
    demo = data_io.read_json(data_io.DATA_DIR / "drugs_demo.json")["drugs"]
    demo_rules = web_build._clean(data_io.read_json(data_io.DATA_DIR / "rules_demo.json"))
    for n in (2, 3, 4):
        for combo in combinations(demo, n):
            out.append({"id": "demo:" + "+".join(d["name"] for d in combo), "drugs": list(combo), "rules": demo_rules})
    for n in (2, 3, 4):
        for combo in combinations(SPECIAL_DRUGS, n):
            out.append({"id": "special:" + "+".join(d["name"] for d in combo), "drugs": list(combo),
                        "rules": SPECIAL_RULES})
    for seed in (0, 1, 2):
        drugs, rules = generator.generate_raw(seed, CFG["virtual"], 20)
        for a, b in combinations(drugs, 2):
            out.append({"id": f"v{seed}:{a['name']}+{b['name']}", "drugs": [a, b], "rules": rules})
        rng = random.Random(seed)
        for idx in rng.sample(list(combinations(range(20), 3)), 40):
            combo = [drugs[i] for i in idx]
            out.append({"id": f"v{seed}:" + "+".join(d["name"] for d in combo), "drugs": combo, "rules": rules})
    return out


def python_side(case):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        drugs = [data_io.parse_drug(d, set(ENZ)) for d in case["drugs"]]
        rules = data_io.parse_rules(case["rules"])
        res = interpret.analyze(drugs, rules, CFG, check=True)
        trace, _ = calc_trace.build(drugs, rules, CFG, res)
    as_json = json.loads(json.dumps({"drugs": drugs, "result": res}))
    return {**as_json, "warnings": [str(w.message) for w in caught], "trace": trace}


@pytest.fixture(scope="module")
def js_results():
    all_cases = cases()
    payload = json.dumps({"config": {"judgement": CFG["judgement"], "flag": CFG["flag"]},
                          "enzymes": ENZ, "cases": all_cases})
    proc = subprocess.run([NODE, str(ROOT / "webtest" / "run_cases.mjs")], input=payload, capture_output=True,
                          text=True, encoding="utf-8", check=True)
    return all_cases, {r["id"]: r for r in json.loads(proc.stdout)}


def test_node_unit_tests_T1_to_T15_and_E2E():
    proc = subprocess.run([NODE, "--test", str(ROOT / "webtest" / "core.test.mjs")], capture_output=True,
                          text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-3000:]
    assert "# fail 0" in proc.stdout


def test_js_equals_python_exactly(js_results):
    all_cases, js = js_results
    assert len(all_cases) > 700
    for case in all_cases:
        py = python_side(case)
        got = js[case["id"]]
        assert "error" not in got, (case["id"], got.get("error"))
        assert got["drugs"] == py["drugs"], case["id"]
        assert got["result"] == py["result"], case["id"]      # 실수까지 비트 단위로 같음
        assert got["warnings"] == py["warnings"], case["id"]
        assert got["trace"] == py["trace"], case["id"]


def test_js_reports_same_input_errors(tmp_path):
    bad = [
        {"name": "X", "metabolism": {"CYP3A4": v(f=0.5, g=0)}},
        {"name": "X", "metabolism": {"CYP3A": v(f=0.6, g=0), "CYP2D6": v(f=0.5, g=0)}},
        {"name": "X", "inhibits": {"CYP3A": v(s=1.0, t=0)}},
        {"name": "X", "actions": {"P": v(type="antagonist", e=0.4)}},
        {"name": "X", "actions": {"P": v(type="agonist", F=0.5, dose=100, CL=10, tau=12, KB=1)}},
        {"name": "X", "induces": {"CYP3A": {"u": 0.5}}},
    ]
    payload = json.dumps({"config": CFG, "enzymes": ENZ,
                          "cases": [{"id": str(i), "drugs": [d], "rules": {"effects": {}}} for i, d in enumerate(bad)]})
    proc = subprocess.run([NODE, str(ROOT / "webtest" / "run_cases.mjs")], input=payload, capture_output=True,
                          text=True, encoding="utf-8", check=True)
    for i, got in enumerate(json.loads(proc.stdout)):
        with pytest.raises(data_io.DataError) as err:
            data_io.parse_drug(bad[i], set(ENZ))
        assert got.get("error") == str(err.value)


def test_web_data_is_up_to_date():
    assert web_build.main(["--check"]) == 0
