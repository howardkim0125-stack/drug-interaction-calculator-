"""예시 가상 약으로 전체 계산을 보여 준다.

사용: python run_demo.py [약 이름 ...] [--drugs 파일] [--rules 파일] [--prefix 이름]
"""
import argparse
import sys

import data_io
import explain
import interpret


def main(argv=None):
    ap = argparse.ArgumentParser(description="약 상호작용 계산 데모")
    ap.add_argument("names", nargs="*", help="함께 먹을 약 이름(생략하면 파일의 모든 약)")
    ap.add_argument("--drugs", default=str(data_io.DATA_DIR / "drugs_demo.json"))
    ap.add_argument("--rules", default=str(data_io.DATA_DIR / "rules_demo.json"))
    ap.add_argument("--config", default=str(data_io.ROOT / "config.json"))
    ap.add_argument("--prefix", default="demo")
    ap.add_argument("--out", default=str(data_io.OUT_DIR))
    args = ap.parse_args(argv)

    cfg = data_io.load_config(args.config)
    drugs = data_io.load_drugs(args.drugs)
    rules = data_io.load_rules(args.rules)
    if args.names:
        by_name = {d["name"]: d for d in drugs}
        missing = [n for n in args.names if n not in by_name]
        if missing:
            sys.exit(f"파일에 없는 약: {missing}")
        drugs = [by_name[n] for n in args.names]

    res = interpret.analyze(drugs, rules, cfg)
    print(explain.format_report(res, cfg))
    paths = explain.write_outputs(res, cfg, args.out, args.prefix)
    print("\n저장: " + ", ".join(str(p.relative_to(data_io.ROOT)) if p.is_relative_to(data_io.ROOT) else str(p)
                                 for p in paths))
    return res


if __name__ == "__main__":
    main()
