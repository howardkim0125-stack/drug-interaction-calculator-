"""입력 파일(약 정보, 이름 목록, 규칙표, 설정) 읽기와 검사."""
import copy
import json
import math
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "out"

DISCLAIMER = "수학 탐구 모델의 결과이며 실제 복약 판단이 아니다."

DEFAULT_CONFIG = {
    "judgement": {
        "b0_small": 0.05,
        "ratio_up": 1.05,
        "ratio_down": 0.95,
        "diff_small": 0.05,
        "cause_min": 0.05,
    },
    "flag": {"r_high": 1.25, "r_low": 0.8},
}

DRUG_KEYS = {"name", "dose_ratio", "metabolism", "inhibits", "induces", "actions"}
ACTION_TYPES = ("agonist", "antagonist")
SUM_TOL = 1e-9


class DataError(ValueError):
    """입력 형식 오류."""


class DataWarning(UserWarning):
    """입력 형식 경고."""


def _warn(msg):
    warnings.warn(msg, DataWarning, stacklevel=2)


def read_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _num(item, key, where, lo=None, hi=None, lo_open=False, hi_open=False):
    if key not in item or item[key] is None:
        raise DataError(f"{where}: '{key}' 값이 없다")
    v = item[key]
    if not _is_num(v):
        raise DataError(f"{where}: '{key}'는 숫자여야 한다 (받은 값: {v!r})")
    v = float(v)
    if lo is not None and (v < lo or (lo_open and v == lo)):
        raise DataError(f"{where}: '{key}' = {v} 범위 밖 ({'>' if lo_open else '≥'} {lo} 이어야 함)")
    if hi is not None and (v > hi or (hi_open and v == hi)):
        raise DataError(f"{where}: '{key}' = {v} 범위 밖 ({'<' if hi_open else '≤'} {hi} 이어야 함)")
    return v


def _source(item, where):
    if "source" not in item:
        raise DataError(f"{where}: 'source'(출처) 칸이 없다")
    src = item["source"]
    if not isinstance(src, str):
        raise DataError(f"{where}: 'source'는 문자열이어야 한다")
    if not src.strip():
        _warn(f"{where}: 출처(source)가 비어 있다")
    return src


def _check_keys(item, allowed, where):
    extra = [k for k in item if k not in allowed and not k.startswith("_")]
    if extra:
        _warn(f"{where}: 알 수 없는 칸 {extra}는 무시한다")


def _section(raw, key, where):
    sec = raw.get(key, {})
    if sec is None:
        sec = {}
    if not isinstance(sec, dict):
        raise DataError(f"{where}: '{key}'는 {{이름: 값}} 형태여야 한다")
    return sec


def _check_enzyme(enz, enzymes, where):
    if enzymes is not None and enz not in enzymes:
        raise DataError(f"{where}: 허용되지 않은 효소 이름 '{enz}' (data/names.json 참고)")


# ---------------------------------------------------------------- 이름 목록

def load_names(path=DATA_DIR / "names.json"):
    raw = read_json(path)
    enz = raw.get("enzymes") if isinstance(raw, dict) else None
    if not isinstance(enz, list) or not enz or not all(isinstance(x, str) and x for x in enz):
        raise DataError(f"{path}: 'enzymes'는 이름 문자열 목록이어야 한다")
    if len(set(enz)) != len(enz):
        raise DataError(f"{path}: 효소 이름이 중복되었다")
    return {"enzymes": set(enz)}


# ---------------------------------------------------------------- 약 정보

def parse_drug(raw, enzymes=None):
    """약 하나를 검사하고 계산용 형태로 바꾼다.

    결과: inhibits는 s, t로, actions는 c로 통일한다(dose_ratio는 계산 때 적용).
    """
    if not isinstance(raw, dict):
        raise DataError("약 정보는 객체({...})여야 한다")
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        raise DataError("약 'name'이 비어 있다")
    where = f"약 {name}"
    _check_keys(raw, DRUG_KEYS, where)

    dose_ratio = 1.0
    if raw.get("dose_ratio") is not None:
        dose_ratio = _num(raw, "dose_ratio", where, lo=0, lo_open=True)

    drug = {"name": name, "dose_ratio": dose_ratio,
            "metabolism": {}, "inhibits": {}, "induces": {}, "actions": {}}

    for enz, item in _section(raw, "metabolism", where).items():
        w = f"{where} metabolism.{enz}"
        _check_enzyme(enz, enzymes, w)
        if not isinstance(item, dict):
            raise DataError(f"{w}: 값은 객체여야 한다")
        _check_keys(item, {"f", "g", "source"}, w)
        f = _num(item, "f", w, 0, 1)
        g = _num(item, "g", w, 0, 1)
        if f == 0 and g == 0:
            _warn(f"{w}: f, g가 모두 0인 원소는 적지 않는다")
        drug["metabolism"][enz] = {"f": f, "g": g, "source": _source(item, w)}
    if sum(m["f"] for m in drug["metabolism"].values()) > 1 + SUM_TOL:
        raise DataError(f"{where}: f의 합이 1보다 크다")
    if sum(m["g"] for m in drug["metabolism"].values()) > 1 + SUM_TOL:
        raise DataError(f"{where}: g의 합이 1보다 크다")

    for enz, item in _section(raw, "inhibits", where).items():
        w = f"{where} inhibits.{enz}"
        _check_enzyme(enz, enzymes, w)
        if not isinstance(item, dict):
            raise DataError(f"{w}: 값은 객체여야 한다")
        direct = any(k in item for k in ("s", "t"))
        by_ki = any(k in item for k in ("Ki", "conc_liver", "conc_gut"))
        if direct and by_ki:
            raise DataError(f"{w}: s,t 방식과 Ki 방식을 함께 쓸 수 없다")
        if by_ki:
            _check_keys(item, {"Ki", "conc_liver", "conc_gut", "source"}, w)
            ki = _num(item, "Ki", w, lo=0, lo_open=True)
            cl = _num(item, "conc_liver", w, lo=0)
            cg = _num(item, "conc_gut", w, lo=0)
            xl, xg = cl / ki, cg / ki
            s, t = xl / (1 + xl), xg / (1 + xg)
        else:
            _check_keys(item, {"s", "t", "source"}, w)
            s = _num(item, "s", w, 0, 1, hi_open=True)
            t = _num(item, "t", w, 0, 1, hi_open=True)
        if s == 0 and t == 0:
            _warn(f"{w}: s, t가 모두 0인 원소는 적지 않는다")
        drug["inhibits"][enz] = {"s": s, "t": t, "from_ki": by_ki, "source": _source(item, w)}

    for enz, item in _section(raw, "induces", where).items():
        w = f"{where} induces.{enz}"
        _check_enzyme(enz, enzymes, w)
        if not isinstance(item, dict):
            raise DataError(f"{w}: 값은 객체여야 한다")
        _check_keys(item, {"u", "source"}, w)
        u = _num(item, "u", w, lo=0)
        if u == 0:
            _warn(f"{w}: u가 0인 원소는 적지 않는다")
        drug["induces"][enz] = {"u": u, "source": _source(item, w)}

    for tgt, item in _section(raw, "actions", where).items():
        w = f"{where} actions.{tgt}"
        if not isinstance(item, dict):
            raise DataError(f"{w}: 값은 객체여야 한다")
        _check_keys(item, {"type", "c", "e", "source"}, w)
        typ = item.get("type")
        if typ not in ACTION_TYPES:
            raise DataError(f"{w}: type은 'agonist' 또는 'antagonist'여야 한다")
        if "c" in item and "e" in item:
            raise DataError(f"{w}: c와 e를 함께 쓸 수 없다")
        if "e" in item:
            if typ != "agonist":
                raise DataError(f"{w}: e는 작용제(agonist)에만 쓸 수 있다")
            e = _num(item, "e", w, 0, 1, hi_open=True)
            c = e / (1 - e)
        else:
            c = _num(item, "c", w, lo=0)
        if c == 0:
            _warn(f"{w}: 작용 세기가 0인 원소는 적지 않는다")
        drug["actions"][tgt] = {"type": typ, "c": c, "from_e": "e" in item,
                                "source": _source(item, w)}
    return drug


def load_drugs(path, names=None):
    """약 정보 파일을 읽는다. 형식은 [약, ...] 또는 {"drugs": [약, ...]}."""
    if names is None:
        names = load_names()
    raw = read_json(path)
    if isinstance(raw, dict):
        raw = raw.get("drugs")
    if not isinstance(raw, list):
        raise DataError(f"{path}: 약 목록을 찾을 수 없다")
    drugs = [parse_drug(d, names["enzymes"]) for d in raw]
    seen = set()
    for d in drugs:
        if d["name"] in seen:
            raise DataError(f"{path}: 약 이름 '{d['name']}'이 중복되었다")
        seen.add(d["name"])
    return drugs


# ---------------------------------------------------------------- 규칙표

def parse_rules(raw):
    if not isinstance(raw, dict) or not isinstance(raw.get("effects"), dict):
        raise DataError("규칙표에 'effects' 객체가 없다")
    effects = {}
    for name, item in raw["effects"].items():
        w = f"효과 {name}"
        if not isinstance(item, dict):
            raise DataError(f"{w}: 값은 객체여야 한다")
        _check_keys(item, {"up", "down", "k", "threshold", "source"}, w)
        lists = {}
        for key in ("up", "down"):
            lst = item.get(key, [])
            if not isinstance(lst, list) or not all(isinstance(x, str) and x for x in lst):
                raise DataError(f"{w}: '{key}'는 대상 이름 목록이어야 한다")
            if len(set(lst)) != len(lst):
                raise DataError(f"{w}: '{key}'에 같은 대상이 두 번 있다")
            lists[key] = list(lst)
        both = set(lists["up"]) & set(lists["down"])
        if both:
            _warn(f"{w}: {sorted(both)}가 up과 down에 모두 있다")
        if not lists["up"] and not lists["down"]:
            _warn(f"{w}: up, down이 모두 비어 있다")
        k = 1.0 if item.get("k") is None else _num(item, "k", w, lo=0)
        thr = item.get("threshold")
        if thr is not None:
            thr = _num(item, "threshold", w, lo=0, lo_open=True)
        effects[name] = {"up": lists["up"], "down": lists["down"], "k": k,
                         "threshold": thr, "source": _source(item, w)}
    return {"effects": effects}


def load_rules(path=DATA_DIR / "rules.json"):
    return parse_rules(read_json(path))


def rule_targets(rules):
    out = set()
    for eff in rules["effects"].values():
        out.update(eff["up"])
        out.update(eff["down"])
    return out


def check_targets(drugs, rules):
    """규칙표 어느 효과에도 없는 작용 대상을 경고한다."""
    known = rule_targets(rules)
    for d in drugs:
        for tgt in d["actions"]:
            if tgt not in known:
                _warn(f"약 {d['name']}: 대상 '{tgt}'는 규칙표의 어느 효과에도 없다(효과 계산에서 빠짐)")


# ---------------------------------------------------------------- 설정

def _merge(base, extra):
    out = copy.deepcopy(base)
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load_config(path=ROOT / "config.json"):
    raw = read_json(path) if Path(path).exists() else {}
    return _merge(DEFAULT_CONFIG, {k: v for k, v in raw.items() if not k.startswith("_")})
