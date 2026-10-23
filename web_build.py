"""웹앱 데이터 파일(docs/data.js)을 data/와 config.json에서 만든다.

사용: python web_build.py          docs/data.js 다시 만들기
      python web_build.py --check  지금 파일이 data/와 같은지만 확인
"""
import argparse
import json
import sys

import data_io

TARGET = data_io.ROOT / "docs" / "data.js"


def _clean(obj):
    """'_'로 시작하는 안내 칸을 뺀다."""
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items() if not k.startswith("_")}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    return obj


def build_text():
    names = data_io.read_json(data_io.DATA_DIR / "names.json")["enzymes"]
    cfg = data_io.load_config()
    demo = {
        "drugs": _clean(data_io.read_json(data_io.DATA_DIR / "drugs_demo.json")["drugs"]),
        "rules": _clean(data_io.read_json(data_io.DATA_DIR / "rules_demo.json")),
    }

    def dump(obj):
        return json.dumps(obj, ensure_ascii=False, indent=2)

    return (
        "// 자동 생성 파일: python web_build.py 로 다시 만든다(직접 고치지 말 것).\n"
        f"export const ENZYMES = {dump(names)};\n\n"
        f"export const CONFIG = {dump({'judgement': cfg['judgement'], 'flag': cfg['flag']})};\n\n"
        f"export const DEMO_SET = {dump(demo)};\n"
    )


def main(argv=None):
    ap = argparse.ArgumentParser(description="웹앱 데이터 파일 만들기")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    text = build_text()
    if args.check:
        same = TARGET.exists() and TARGET.read_text(encoding="utf-8") == text
        print("docs/data.js가 최신이다" if same else "docs/data.js가 data/와 다르다: python web_build.py 실행")
        return 0 if same else 1
    TARGET.write_text(text, encoding="utf-8")
    print(f"저장: {TARGET.relative_to(data_io.ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
