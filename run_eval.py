"""가상 약 대량 시험 실행 (명세 6-3).

사용:
  python run_eval.py                       기본 평가(config의 seed, 약 20개, 2약 조합 전체)
  python run_eval.py --n-drugs 50 --triples  약 50개 + 무작위 3약 조합
  python run_eval.py --stress              스트레스 시험(요인별 세기 0, 0.1, 0.2, 0.4 × seed 10개)
  python run_eval.py --stress --factors noise transporter --n-drugs 50
"""
import argparse
import json
import math
from datetime import datetime, timezone

import data_io
import evaluate
from data_io import DISCLAIMER, OUT_DIR
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
SERIES_COLOR = {"precision": "#2a78d6", "recall": "#eb6834", "agreement": "#1baf7a", "mae": "#2a78d6"}
# 값이 겹쳐도 둘 다 보이도록 선 모양과 표식도 다르게(나중 것이 점선으로 위에 그려짐)
SERIES_STYLE = {"precision": ("-", "o"), "recall": ("--", "s"), "agreement": (":", "D"), "mae": ("-", "o")}
TEXT_PRIMARY, TEXT_SECONDARY, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
SYMBOL = {"m": "m", "delta": "δ", "q": "q", "eps": "ε"}
KOREAN_FONTS = ["Malgun Gothic", "AppleGothic", "Apple SD Gothic Neo", "NanumGothic",
                "NanumBarunGothic", "Noto Sans CJK KR", "Noto Sans KR", "UnDotum"]


def _series_kind(key):
    for part in SERIES_COLOR:
        if part in key:
            return part
    return "precision"


def _setup_font():
    """한글 글꼴이 있으면 쓰고, 없으면 영어 이름표를 쓴다."""
    from matplotlib import font_manager, rcParams
    have = {f.name for f in font_manager.fontManager.ttflist}
    for name in KOREAN_FONTS:
        if name in have:
            rcParams["font.family"] = name
            rcParams["axes.unicode_minus"] = False
            return True
    return False


def plot_factor(summary_rows, factor, cfg, path, n_seeds):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ko = _setup_font()
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


def main(argv=None):
    ap = argparse.ArgumentParser(description="가상 약 대량 시험")
    ap.add_argument("--config", default=str(data_io.ROOT / "config.json"))
    ap.add_argument("--seed", type=int)
    ap.add_argument("--n-drugs", type=int)
    ap.add_argument("--triples", action="store_true", help="무작위 3약 조합도 평가(개수는 config)")
    ap.add_argument("--stress", action="store_true")
    ap.add_argument("--factors", nargs="+", choices=truth_mod.FACTORS, default=list(truth_mod.FACTORS))
    ap.add_argument("--out", default=str(OUT_DIR))
    args = ap.parse_args(argv)

    from pathlib import Path
    cfg = data_io.load_config(args.config)
    out_dir = Path(args.out)
    ev = cfg["evaluate"]
    triples = ev["triples"] if args.triples else 0
    if args.stress:
        n = args.n_drugs or ev["stress"]["n_drugs"]
        return run_stress(cfg, args.factors, n, triples or ev["stress"]["triples"], out_dir)
    seed = ev["seed"] if args.seed is None else args.seed
    return run_basic(cfg, seed, args.n_drugs or ev["n_drugs"], triples, out_dir)


if __name__ == "__main__":
    main()
