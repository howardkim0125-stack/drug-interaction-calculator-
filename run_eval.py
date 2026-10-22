"""가상 약 대량 시험 실행 (명세 6-3).

사용:
  python run_eval.py                       기본 평가(config의 seed, 약 20개, 2약 조합 전체 + 3약 조합 200개)
  python run_eval.py --no-triples          3약 조합 없이
  python run_eval.py --stress              스트레스 시험(요인별 세기 0, 0.1, 0.2, 0.4 × seed 10개)
  python run_eval.py --compare             비교 모델 1·2와 현재 시스템(seed 10개)
  python run_eval.py --sensitivity         판정 비율 기준 민감도(seed 10개)
  python run_eval.py --all                 위 네 가지 모두
"""
import argparse
import json
import math
from datetime import datetime, timezone

import data_io
import evaluate
from data_io import DISCLAIMER, OUT_DIR
from plotstyle import AQUA, BLUE, GRID, ORANGE, SURFACE, TEXT_PRIMARY, TEXT_SECONDARY, setup_font
from tables import format_table, write_csv
from virtual import generator
from virtual import truth as truth_mod

FACTOR_KO = {"transporter": "수송체", "k_error": "진짜 k 오차", "partial_agonist": "부분 작용제",
             "cascade": "연쇄 효과", "noise": "측정 오차"}
FACTOR_EN = {"transporter": "Transporter", "k_error": "True-k error", "partial_agonist": "Partial agonist",
             "cascade": "Cascade", "noise": "Measurement noise"}
METRIC_KO = dict(evaluate.METRICS)
METRIC_EN = {
    "mech_precision": "Precision", "mech_recall": "Recall",
    "judge_precision": "Precision", "judge_recall": "Recall", "verdict_agreement": "Verdict agreement",
    "manifest_precision": "Precision", "manifest_recall": "Recall",
    "mae_r": "MAE of r", "mae_effect": "MAE of effect value",
}


# ---------------------------------------------------------------- 실행 정보 기록

def log_run(entry, path=OUT_DIR / "run_log.json"):
    """실행 전에 숨은 규칙 설정과 seed 목록을 날짜와 함께 남긴다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    log = []
    if path.exists():
        try:
            log = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            log = []
    entry = {"date": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"), **entry}
    log.append(entry)
    path.write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
    return entry


# ---------------------------------------------------------------- 기본 평가

def run_basic(cfg, seed, n_drugs, triples, out_dir):
    settings = cfg["truth"]
    log_run({"mode": "evaluate", "seeds": [seed], "n_drugs": n_drugs, "triples": triples,
             "truth": settings, "virtual": cfg["virtual"], "judgement": cfg["judgement"]},
            out_dir / "run_log.json")
    res = evaluate.evaluate_world(seed, cfg, settings, n_drugs, triples)
    world_files = generator.save(seed, cfg["virtual"], out_dir, n_drugs)

    mrows = [[key, label, res["metrics"][key]] for key, label in evaluate.METRICS]
    crow = res["counts"]
    count_rows = [[name, c["tp"], c["fp"], c["fn"], c["tn"]]
                  for name, c in (("기전 수준", crow["mech"]), ("판정 수준", crow["judge"]),
                                  ("발현", crow["manifest"]))]
    conf_rows = [[f"시스템 {s}"] + [res["confusion"][(s, t)] for t in evaluate.VERDICTS]
                 for s in evaluate.VERDICTS]
    conf_head = ["", *[f"진짜 {t}" for t in evaluate.VERDICTS]]

    print(f"가상 약 {n_drugs}개, seed {seed}, 2약 조합 + 3약 조합 {triples}개 → 조합 {res['n_combos']}개, "
          f"평가한 (조합, 효과) {res['n_effect_rows']}개")
    print("숨은 요인: " + ", ".join(
        f"{FACTOR_KO[f]} {'끔' if not settings[f]['on'] else ('켬' if f == 'cascade' else truth_mod.strength_of(settings, f))}"
        for f in truth_mod.FACTORS))
    print()
    print(format_table(["지표", "이름", "값"], mrows, "지표"))
    print()
    print(format_table(["수준", "TP(P∩A)", "FP", "FN", "TN"], count_rows, "개수"))
    print()
    print(format_table(conf_head, conf_rows, "판정 혼동표 (행: 시스템, 열: 진짜)"))
    if res["nonconverged"]:
        print(f"\n연쇄 효과가 수렴하지 않은 조합: {res['nonconverged']}개")
    print("\n" + DISCLAIMER)

    write_csv(out_dir / "eval_metrics.csv", ["metric", "name", "value"], mrows)
    write_csv(out_dir / "eval_counts.csv", ["level", "TP", "FP", "FN", "TN"], count_rows)
    write_csv(out_dir / "eval_confusion.csv", ["system\\truth", *evaluate.VERDICTS], conf_rows)
    write_csv(out_dir / "eval_pairs.csv",
              ["changer", "changed", "system_flag", "truth_affected", "system_r", "true_r",
               "hidden_transporter"], res["pair_rows"])
    write_csv(out_dir / "eval_effects.csv",
              ["combo", "effect", "system_B0", "system_Bfull", "true_B0", "true_Bfull",
               "system_verdict", "true_verdict", "system_manifest", "true_manifest"], res["effect_rows"])
    print("저장: out/eval_metrics.csv, eval_counts.csv, eval_confusion.csv, eval_pairs.csv, eval_effects.csv, "
          + ", ".join(p.name for p in world_files))
    return res


# ---------------------------------------------------------------- 그래프

PANELS = [
    ("분류: 기전 수준", "Classification: mechanism", ["mech_precision", "mech_recall"], True),
    ("분류: 판정 수준", "Classification: verdict",
     ["judge_precision", "judge_recall", "verdict_agreement"], True),
    ("발현", "Manifestation", ["manifest_precision", "manifest_recall"], True),
    ("r 평균절대오차", "MAE of r", ["mae_r"], False),
    ("효과 값 평균절대오차", "MAE of effect value", ["mae_effect"], False),
]
# 지표마다 정해진 색(같은 지표는 모든 칸에서 같은 색): 정밀도 파랑, 재현율 주황, 일치율 청록
SERIES_COLOR = {"precision": BLUE, "recall": ORANGE, "agreement": AQUA, "mae": BLUE}
# 값이 겹쳐도 둘 다 보이도록 선 모양과 표식도 다르게(나중 것이 점선으로 위에 그려짐)
SERIES_STYLE = {"precision": ("-", "o"), "recall": ("--", "s"), "agreement": (":", "D"), "mae": ("-", "o")}
SYMBOL = {"m": "m", "delta": "δ", "q": "q", "eps": "ε"}


def _series_kind(key):
    for part in SERIES_COLOR:
        if part in key:
            return part
    return "precision"


def plot_factor(summary_rows, factor, cfg, path, n_seeds):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ko = setup_font()
    data = {}
    for f, strength, metric, mean, lo, hi, _ in summary_rows:
        if f == factor:
            data.setdefault(metric, []).append((strength, mean, lo, hi))
    for v in data.values():
        v.sort()

    fig, axes = plt.subplots(1, len(PANELS), figsize=(18, 4.2), facecolor=SURFACE)
    for ax, (title_ko, title_en, metrics, is_rate) in zip(axes, PANELS):
        ax.set_facecolor(SURFACE)
        for metric in metrics:
            pts = [p for p in data.get(metric, []) if not math.isnan(p[1])]
            if not pts:
                continue
            xs = [p[0] for p in pts]
            kind = _series_kind(metric)
            color = SERIES_COLOR[kind]
            linestyle, marker = SERIES_STYLE[kind]
            label = METRIC_KO[metric].split(" ")[-1] if ko else METRIC_EN[metric]
            ax.fill_between(xs, [p[2] for p in pts], [p[3] for p in pts], color=color, alpha=0.15,
                            linewidth=0)
            ax.plot(xs, [p[1] for p in pts], color=color, linewidth=2, linestyle=linestyle,
                    marker=marker, markersize=6,
                    markeredgecolor=SURFACE, markeredgewidth=1.5, label=label)
        ax.set_title(title_ko if ko else title_en, color=TEXT_PRIMARY, fontsize=11, loc="left")
        if is_rate:
            ax.set_ylim(-0.02, 1.04)
        else:
            top = max([p[3] for m in metrics for p in data.get(m, []) if not math.isnan(p[3])] or [0])
            ax.set_ylim(0, max(top * 1.1, 0.01))
        if factor == "cascade":
            ax.set_xticks([0, 1])
            ax.set_xticklabels(["끔", "켬"] if ko else ["off", "on"])
            ax.set_xlim(-0.3, 1.3)
        else:
            ax.set_xticks(cfg["evaluate"]["stress"]["strengths"])
        key = SYMBOL.get(truth_mod.STRENGTH_KEY[factor], "")
        ax.set_xlabel(("세기 " if ko else "strength ") + key,
                      color=TEXT_SECONDARY)
        ax.grid(axis="y", color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(GRID)
        ax.tick_params(colors=TEXT_SECONDARY, labelsize=9)

    if ko:
        fixed = "" if factor != "transporter" else f", p = {cfg['truth']['transporter']['p']} 고정"
        title = (f"숨은 요인: {FACTOR_KO[factor]}{fixed} (나머지 요인 끔) — "
                 f"seed {n_seeds}개 평균, 띠는 최솟값~최댓값")
        foot = DISCLAIMER
    else:
        title = (f"Hidden factor: {FACTOR_EN[factor]} (others off) — mean of {n_seeds} seeds, "
                 f"band = min to max")
        foot = "Result of a math-inquiry model; not a real medication decision."
    from matplotlib.lines import Line2D
    names = {"precision": ("정밀도", "Precision"), "recall": ("재현율", "Recall"),
             "agreement": ("판정 일치율(3×3)", "Verdict agreement (3×3)")}
    handles = [Line2D([], [], color=SERIES_COLOR[k], linewidth=2, linestyle=SERIES_STYLE[k][0],
                      marker=SERIES_STYLE[k][1], markersize=6, markeredgecolor=SURFACE,
                      label=names[k][0 if ko else 1]) for k in names]
    fig.legend(handles=handles, loc="upper right", ncol=3, frameon=False, fontsize=10,
               labelcolor=TEXT_SECONDARY, bbox_to_anchor=(0.99, 0.995))
    fig.suptitle(title, x=0.01, ha="left", color=TEXT_PRIMARY, fontsize=12)
    fig.text(0.01, 0.01, foot, color=TEXT_SECONDARY, fontsize=9)
    fig.tight_layout(rect=(0, 0.04, 1, 0.94))
    fig.savefig(path, dpi=130, facecolor=SURFACE)
    plt.close(fig)
    return path


# ---------------------------------------------------------------- 스트레스 시험

def run_stress(cfg, factors, n_drugs, triples, out_dir, seeds=None):
    sc = cfg["evaluate"]["stress"]
    seeds = sc["seeds"] if seeds is None else seeds
    log_run({"mode": "stress", "factors": list(factors), "strengths": sc["strengths"],
             "others": "off", "seeds": seeds, "n_drugs": n_drugs, "triples": triples,
             "truth": cfg["truth"], "virtual": cfg["virtual"], "judgement": cfg["judgement"]},
            out_dir / "run_log.json")

    def progress(factor, level, seed):
        if seed == seeds[-1]:
            print(f"  {FACTOR_KO[factor]} 세기 {level} 완료")

    runs = evaluate.stress(cfg, factors, seeds, sc["strengths"], n_drugs, triples, progress)
    keys = [k for k, _ in evaluate.METRICS]
    write_csv(out_dir / "stress_runs.csv", ["factor", "strength", "seed", "nonconverged", *keys],
              [[r["factor"], r["strength"], r["seed"], r["nonconverged"], *[r[k] for k in keys]]
               for r in runs])
    head, rows = evaluate.summarize(runs)
    write_csv(out_dir / "stress_summary.csv", head, rows)

    print()
    for factor in factors:
        frows = [r for r in rows if r[0] == factor]
        levels = sorted({r[1] for r in frows})
        table = []
        for key, label in evaluate.METRICS:
            cells = []
            for lv in levels:
                mean, lo, hi = next((r[3], r[4], r[5]) for r in frows if r[1] == lv and r[2] == key)
                cells.append("-" if math.isnan(mean) else f"{mean:.3f} [{lo:.3f}, {hi:.3f}]")
            table.append([label, *cells])
        names = ["끔", "켬"] if factor == "cascade" else [f"{SYMBOL[truth_mod.STRENGTH_KEY[factor]]}={lv:g}" for lv in levels]
        print(format_table(["지표 (평균 [최소, 최대])", *names], table, f"스트레스 시험: {FACTOR_KO[factor]}"))
        print()
        plot_factor(rows, factor, cfg, out_dir / f"stress_{factor}.png", len(seeds))
    print(DISCLAIMER)
    print("저장: out/stress_runs.csv, out/stress_summary.csv, "
          + ", ".join(f"out/stress_{f}.png" for f in factors) + ", out/run_log.json")
    return runs, rows


# ---------------------------------------------------------------- 비교 모델과 판정 기준 민감도

MODEL_COLOR = {"system": BLUE, "simple_sum": ORANGE, "proportional": AQUA}
MODEL_EN = {"system": "Current system", "simple_sum": "Model 1: simple sum",
            "proportional": "Model 2: proportional"}
METRIC_FULL_EN = {
    "mech_precision": "Mechanism precision", "mech_recall": "Mechanism recall",
    "mech_accuracy": "Mechanism accuracy", "judge_precision": "Verdict-level precision",
    "judge_recall": "Verdict-level recall", "judge_accuracy": "Verdict-level accuracy",
    "mae_r": "MAE of r", "mae_effect": "MAE of effect value",
    "verdict_agreement": "Verdict agreement (3×3)", "manifest_precision": "Manifestation precision",
    "manifest_recall": "Manifestation recall",
}
SENS_METRICS = ["verdict_agreement", "judge_precision", "judge_recall"]


def build_worlds(cfg, seeds, n_drugs, triples):
    return [evaluate.build_world(seed, cfg, cfg["truth"], n_drugs, triples) for seed in seeds]


def plot_models(rows, path, n_seeds):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ko = setup_font()
    stats = {(m, k): (mean, lo, hi) for m, k, mean, lo, hi, _ in rows}
    rate_keys = [k for k, _ in evaluate.METRICS if not k.startswith("mae")]
    mae_keys = ["mae_r", "mae_effect"]
    models = list(evaluate.MODELS)
    fig, axes = plt.subplots(1, 2, figsize=(14, 7.5), facecolor=SURFACE,
                             gridspec_kw={"width_ratios": [3, 2]})
    height = 0.8 / len(models)
    for ax, keys, title in ((axes[0], rate_keys, ("비율 지표", "Rate metrics")),
                            (axes[1], mae_keys, ("평균절대오차(MAE)", "Mean absolute error"))):
        ax.set_facecolor(SURFACE)
        top = 0.0
        for i, key in enumerate(keys):
            for j, model in enumerate(models):
                y = i + (j - (len(models) - 1) / 2) * height
                mean, lo, hi = stats[(model, key)]
                if math.isnan(mean):
                    ax.text(0.005, y, "값 없음" if ko else "n/a", va="center", fontsize=8,
                            color=TEXT_SECONDARY)
                    continue
                if mean == 0:
                    ax.text(0.005, y, "0", va="center", fontsize=8, color=TEXT_SECONDARY)
                ax.barh(y, mean, height=height * 0.85, color=MODEL_COLOR[model], linewidth=0)
                ax.plot([lo, hi], [y, y], color=TEXT_SECONDARY, linewidth=1)
                top = max(top, hi)
        ax.set_yticks(range(len(keys)))
        ax.set_yticklabels([METRIC_KO[k] if ko else METRIC_FULL_EN[k] for k in keys], color=TEXT_PRIMARY)
        ax.invert_yaxis()
        ax.set_xlim(0, 1.0 if ax is axes[0] else max(top * 1.15, 0.01))
        ax.set_title(title[0] if ko else title[1], color=TEXT_PRIMARY, fontsize=11, loc="left")
        ax.grid(axis="x", color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(GRID)
        ax.tick_params(colors=TEXT_SECONDARY, labelsize=9)
    from matplotlib.patches import Patch
    handles = [Patch(color=MODEL_COLOR[m], label=evaluate.MODEL_KO[m] if ko else MODEL_EN[m]) for m in models]
    fig.legend(handles=handles, loc="upper right", ncol=3, frameon=False, fontsize=10,
               labelcolor=TEXT_SECONDARY, bbox_to_anchor=(0.99, 0.995))
    if ko:
        title = f"비교 모델과 현재 시스템 — 같은 숨은 세계(기본 세기), seed {n_seeds}개 평균, 가는 선은 최솟값~최댓값"
        foot = DISCLAIMER
    else:
        title = f"Comparison models vs current system — same hidden worlds, mean of {n_seeds} seeds, line = min to max"
        foot = "Result of a math-inquiry model; not a real medication decision."
    fig.suptitle(title, x=0.01, ha="left", color=TEXT_PRIMARY, fontsize=12)
    fig.text(0.01, 0.01, foot, color=TEXT_SECONDARY, fontsize=9)
    fig.tight_layout(rect=(0, 0.03, 1, 0.93))
    fig.savefig(path, dpi=130, facecolor=SURFACE)
    plt.close(fig)
    return path


def _cell(mean, lo, hi):
    return "-" if math.isnan(mean) else f"{mean:.3f} [{lo:.3f}, {hi:.3f}]"


def run_compare_and_sensitivity(cfg, out_dir, do_compare=True, do_sensitivity=True, n_drugs=None):
    mc = cfg["evaluate"]["multi"]
    seeds, triples = mc["seeds"], mc["triples"]
    n_drugs = n_drugs or mc["n_drugs"]
    thresholds = [tuple(x) for x in cfg["evaluate"]["sensitivity"]["ratios"]]
    log_run({"mode": "compare/sensitivity", "compare": do_compare, "sensitivity": do_sensitivity,
             "seeds": seeds, "n_drugs": n_drugs, "triples": triples, "ratio_thresholds": thresholds,
             "truth": cfg["truth"], "virtual": cfg["virtual"], "judgement": cfg["judgement"]},
            out_dir / "run_log.json")
    worlds = build_worlds(cfg, seeds, n_drugs, triples)
    keys = [k for k, _ in evaluate.METRICS]
    out = {}

    if do_compare:
        runs = evaluate.compare_models(worlds, cfg)
        head, rows = evaluate.summarize_by(runs, "model", keys)
        write_csv(out_dir / "compare_models_runs.csv", ["model", "seed", *keys],
                  [[r["model"], r["seed"], *[r[k] for k in keys]] for r in runs])
        write_csv(out_dir / "compare_models.csv", head, rows)
        stats = {(m, k): (mean, lo, hi) for m, k, mean, lo, hi, _ in rows}
        table = [[label, *[_cell(*stats[(m, k)]) for m in evaluate.MODELS]] for k, label in evaluate.METRICS]
        print(format_table(["지표 (평균 [최소, 최대])", *[evaluate.MODEL_KO[m] for m in evaluate.MODELS]],
                           table, f"비교 모델 (약 {n_drugs}개, 2약 전체 + 3약 {triples}개, seed {len(seeds)}개)"))
        print()
        plot_models(rows, out_dir / "compare_models.png", len(seeds))
        out["compare"] = rows

    if do_sensitivity:
        runs = evaluate.sensitivity(worlds, cfg, thresholds)
        head, rows = evaluate.summarize_by(runs, "thresholds", SENS_METRICS)
        write_csv(out_dir / "sensitivity_runs.csv", ["thresholds", "seed", *SENS_METRICS],
                  [[r["thresholds"], r["seed"], *[r[k] for k in SENS_METRICS]] for r in runs])
        write_csv(out_dir / "sensitivity.csv", head, rows)
        stats = {(g, k): (mean, lo, hi) for g, k, mean, lo, hi, _ in rows}
        labels = [f"{u:g}/{d:g}" for u, d in thresholds]
        table = [[METRIC_KO[k], *[_cell(*stats[(g, k)]) for g in labels]] for k in SENS_METRICS]
        print(format_table(["지표 (평균 [최소, 최대])", *[f"기준 {g}" for g in labels]], table,
                           "판정 기준 민감도 (시스템·진짜 양쪽에 같은 기준)"))
        print()
        out["sensitivity"] = rows

    print(DISCLAIMER)
    saved = []
    if do_compare:
        saved += ["compare_models.csv", "compare_models_runs.csv", "compare_models.png"]
    if do_sensitivity:
        saved += ["sensitivity.csv", "sensitivity_runs.csv"]
    print("저장: " + ", ".join(f"out/{x}" for x in saved))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="가상 약 대량 시험")
    ap.add_argument("--config", default=str(data_io.ROOT / "config.json"))
    ap.add_argument("--seed", type=int)
    ap.add_argument("--n-drugs", type=int)
    ap.add_argument("--no-triples", action="store_true", help="기본 평가에서 3약 조합을 빼기")
    ap.add_argument("--stress", action="store_true", help="스트레스 시험")
    ap.add_argument("--compare", action="store_true", help="비교 모델 평가")
    ap.add_argument("--sensitivity", action="store_true", help="판정 기준 민감도")
    ap.add_argument("--all", action="store_true", help="기본 평가, 스트레스 시험, 비교 모델, 민감도 모두")
    ap.add_argument("--factors", nargs="+", choices=truth_mod.FACTORS, default=list(truth_mod.FACTORS))
    ap.add_argument("--out", default=str(OUT_DIR))
    args = ap.parse_args(argv)

    from pathlib import Path
    cfg = data_io.load_config(args.config)
    out_dir = Path(args.out)
    ev = cfg["evaluate"]
    basic = args.all or not (args.stress or args.compare or args.sensitivity)
    result = {}
    if basic:
        seed = ev["seed"] if args.seed is None else args.seed
        triples = 0 if args.no_triples else ev["triples"]
        result["basic"] = run_basic(cfg, seed, args.n_drugs or ev["n_drugs"], triples, out_dir)
    if args.stress or args.all:
        n = args.n_drugs or ev["stress"]["n_drugs"]
        result["stress"] = run_stress(cfg, args.factors, n, ev["stress"]["triples"], out_dir)
    if args.compare or args.sensitivity or args.all:
        result.update(run_compare_and_sensitivity(cfg, out_dir, args.compare or args.all,
                                                  args.sensitivity or args.all, args.n_drugs))
    return result["basic"] if list(result) == ["basic"] else result


if __name__ == "__main__":
    main()
