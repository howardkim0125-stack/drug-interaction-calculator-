"""템플릿 설명 문장과 출력 (명세 4). AI 호출 없음."""
from pathlib import Path

from classify import format_classification
from data_io import DISCLAIMER
from tables import format_table, write_csv

EPS = 1e-9
TYPE_KO = {"agonist": "작용제", "antagonist": "차단제"}
DIR_KO = {"up": "올림", "down": "내림"}


def k_meaning(k):
    if k == 0:
        return "같은 대상처럼 그냥 더함"
    if k == 1:
        return "서로 따로 작용"
    if k > 1:
        return "서로 도움(시너지)"
    return "일부 겹침"


def _sgn(v):
    return f"{v:+.4f}"


def concentration_evidence(name, info):
    """약 하나의 평균 농도 변화 근거 문장."""
    pieces = []
    for enz, rem in info["enzymes"].items():
        if not rem["inhibitors"] and not rem["inducers"]:
            continue
        who = [f"{n}가 억제(s={s:.2f}, t={t:.2f})" for n, s, t in rem["inhibitors"]]
        who += [f"{n}가 유도(u={u:.2f})" for n, u in rem["inducers"]]
        pieces.append(f"{enz}(f={rem['f']:.2f}, g={rem['g']:.2f})를 {', '.join(who)} → 남은 작용 간 {rem['a_liver']:.3f}, 장 {rem['a_gut']:.3f}")
    if not pieces:
        return None
    return (f"약 {name}의 분해 효소 " + "; ".join(pieces)
            + f" → r = {info['r']:.4f} (간 {info['r_liver']:.4f} × 장 {info['r_gut']:.4f})")


def explain_effect(e, ratios, cfg):
    """효과 하나의 설명 문단."""
    j = cfg["judgement"]
    rule = e["rule"]
    lines = []
    if e["R"] is not None:
        how = f"R = B_full ÷ B₀ = {e['R']:.3f} (독립 범위 {j['ratio_down']}~{j['ratio_up']})"
    else:
        how = (f"|B₀| < {j['b0_small']}이라 차이로 판정: d = {_sgn(e['d'])} "
               f"(독립 범위 ±{j['diff_small']})")
    lines.append(f"[{e['effect']}] 판정: {e['verdict']} — {how}")
    if e["B0"] * e["Bfull"] < 0:
        lines.append("  참고: B₀와 B_full의 부호가 반대 → 효과 방향이 뒤집힘(B₀ 방향 기준으로 감소)")
    lines.append(f"  수치: 기준값 B₀ = {e['B0']:.4f}, r만 반영 B_r = {e['Br']:.4f}, "
                 f"실제값 B_full = {e['Bfull']:.4f}")
    lines.append(f"  원인 분해: r 기여 {_sgn(e['r_contrib'])}, k 기여 {_sgn(e['k_contrib'])} "
                 f"→ 원인: {e['cause']}")

    for name in e["involved"]:
        info = ratios[name]
        if abs(info["r"] - 1) > EPS:
            ev = concentration_evidence(name, info)
            if ev:
                lines.append(f"  근거(평균 농도): {ev}")

    for tgt, t in e["targets"].items():
        parts = [f"{n}(작용제 c′={c:.4f})" for n, c in t["ag"]]
        parts += [f"{n}(차단제 c′={c:.4f})" for n, c in t["ant"]]
        shared = "함께 작용" if len(parts) > 1 else "작용"
        lines.append(f"  근거(대상): {tgt}[{DIR_KO[t['dir']]}]에 {', '.join(parts)}가 {shared} "
                     f"→ E = {t['E0']:.4f}(기준) → {t['E']:.4f}(실제)")

    active = {d: [t for t, v in e["targets"].items() if v["dir"] == d] for d in ("up", "down")}
    multi = [d for d in ("up", "down") if len(active[d]) > 1]
    if multi:
        groups = ", ".join(f"{DIR_KO[d]} 묶음 {active[d]}" for d in multi)
        lines.append(f"  근거(효과 묶음): 서로 다른 대상 {groups}이 같은 효과로 이어짐, "
                     f"k = {rule['k']:g} ({k_meaning(rule['k'])})")

    if rule["threshold"] is not None:
        singles = ", ".join(f"{n} {v:.4f}" for n, v in e["singles"].items())
        state = "발현" if e["manifest"] else "발현 아님"
        lines.append(f"  발현: {state} — {e['manifest_kind']} "
                     f"(기준 {rule['threshold']:g}, 단독 값: {singles}, |B_full| = {abs(e['Bfull']):.4f})")
    return "\n".join(lines)


def ratio_rows(res):
    rows = []
    for name in res["drugs"]:
        v = res["ratios"][name]
        rows.append([name, v["r_liver"], v["r_gut"], v["r"], v["flag"] or ""])
    return ["약", "r_간", "r_장", "r", "평균 농도 변화"], rows


def effect_rows(res, only_involved=False):
    headers = ["효과", "관련 약", "B0", "B_r", "B_full", "R", "d", "판정",
               "r 기여", "k 기여", "원인", "기준(threshold)", "발현", "발현 구분"]
    rows = []
    for e in res["effects"]:
        if only_involved and not e["involved"]:
            continue
        shown = "-" if e["manifest"] is None else ("발현" if e["manifest"] else "아님")
        rows.append([e["effect"], " ".join(e["involved"]) or "-", e["B0"], e["Br"], e["Bfull"],
                     e["R"], e["d"], e["verdict"], e["r_contrib"], e["k_contrib"], e["cause"],
                     e["rule"]["threshold"], shown, e["manifest_kind"]])
    return headers, rows


def classification_rows(res):
    cls = res["classification"]
    rows = [["평균 농도", c["from"], c["to"], ", ".join(c["how"]), ""] for c in cls["concentration"]]
    rows += [["같은 대상", s["a"], s["b"], s["target"], s["label"]] for s in cls["same_target"]]
    rows += [["같은 효과", s["a"], s["b"], f"{s['effect']}: {s['target_a']}({s['dir_a']}) / "
              f"{s['target_b']}({s['dir_b']})", "같은 방향" if s["same_dir"] else "반대 방향"]
             for s in cls["same_effect"]]
    return ["종류", "약 1(바꾸는 약)", "약 2(바뀌는 약)", "겹친 이름", "비고"], rows


def flag_lines(res, cfg):
    f = cfg["flag"]
    out = []
    for name in res["drugs"]:
        v = res["ratios"][name]
        if v["flag"]:
            out.append(f"  {name}: r = {v['r']:.4f} → {v['flag']} (기준 r ≥ {f['r_high']} 또는 r ≤ {f['r_low']})")
    return out


def format_report(res, cfg):
    parts = [f"함께 먹는 약: {', '.join(res['drugs'])}", "", format_classification(res["classification"]), ""]
    h, rows = ratio_rows(res)
    parts += [format_table(h, rows, "평균 농도 변화 r"), ""]
    flags = flag_lines(res, cfg)
    parts += ["[평균 농도 변화 표시]"] + (flags or ["  해당 약 없음"]) + [""]
    h, rows = effect_rows(res, only_involved=True)
    parts += [format_table(h, rows, "효과별 결과 (관련 약이 있는 효과만)"), ""]
    parts.append("[설명]")
    for e in res["effects"]:
        if e["involved"]:
            parts += [explain_effect(e, res["ratios"], cfg), ""]
    parts.append(DISCLAIMER)
    return "\n".join(parts)


def write_outputs(res, cfg, out_dir, prefix):
    out_dir = Path(out_dir)
    paths = [
        write_csv(out_dir / f"{prefix}_classification.csv", *classification_rows(res)),
        write_csv(out_dir / f"{prefix}_ratios.csv", *ratio_rows(res)),
        write_csv(out_dir / f"{prefix}_effects.csv", *effect_rows(res)),
    ]
    report = out_dir / f"{prefix}_report.txt"
    report.write_text(format_report(res, cfg) + "\n", encoding="utf-8")
    paths.append(report)
    return paths

