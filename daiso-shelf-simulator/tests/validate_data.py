#!/usr/bin/env python3
"""데이터 검증: data/baskets.json / baskets.js 가 실제 다이소몰 수집값인지 형태를 확인한다.

실행: python3 tests/validate_data.py
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_JSON = os.path.join(ROOT, "data", "baskets.json")
DATA_JS = os.path.join(ROOT, "data", "baskets.js")

fails = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + (("  " + str(detail)) if detail else ""))
    if not cond:
        fails.append(name)


def main():
    data = json.load(open(DATA_JSON, encoding="utf-8"))
    items = data["items"]
    meta = data["meta"]

    check("상품 수 40개 이상", len(items) >= 40, len(items))
    check("meta.count 일치", meta.get("count") == len(items), meta.get("count"))

    ids = [i["id"] for i in items]
    check("품번 중복 없음", len(ids) == len(set(ids)))

    bad_code = [i["id"] for i in items if not re.fullmatch(r"[0-9A-Za-z]{4,20}", str(i["id"]))]
    check("품번 형식", not bad_code, bad_code[:5])

    bad_num = []
    for i in items:
        for k in ("w", "d", "h"):
            v = i.get(k)
            if not isinstance(v, (int, float)) or v != v or v <= 0:
                bad_num.append((i["id"], k, v))
    check("규격 값 유효(양수·NaN 없음)", not bad_num, bad_num[:5])

    out_range = [i["id"] for i in items if not (2 <= i["w"] <= 120 and 2 <= i["d"] <= 120 and 2 <= i["h"] <= 120)]
    check("규격 범위(2~120cm)", not out_range, out_range[:5])

    bad_price = [i["id"] for i in items if not isinstance(i["price"], int) or i["price"] <= 0]
    check("가격 유효", not bad_price, bad_price[:5])

    bad_url = [i["id"] for i in items
               if str(i.get("pd", "")) not in str(i.get("url", "")) and str(i.get("url", "")).find(i["id"]) < 0]
    check("상품 URL에 상품번호 포함", not bad_url, bad_url[:5])

    no_series = [i["id"] for i in items if not i.get("series")]
    check("시리즈 태그 존재", not no_series, no_series[:5])

    no_name = [i["id"] for i in items if not i.get("name")]
    check("품명 존재", not no_name, no_name[:5])

    srcs = set(i.get("src") for i in items)
    check("규격 출처 표기", srcs <= {"label", "desc"}, srcs)

    # JS 파일이 JSON 과 같은 데이터인지
    js = open(DATA_JS, encoding="utf-8").read()
    m = re.search(r"window\.DAISO_DATA\s*=\s*(\{.*\});\s*$", js, re.S)
    check("baskets.js 형식", bool(m))
    if m:
        same = json.loads(m.group(1)) == data
        check("baskets.js == baskets.json", same)

    # 요약
    prices = sorted(set(i["price"] for i in items))
    series = {}
    for i in items:
        for s in i["series"]:
            series[s] = series.get(s, 0) + 1
    print("\n가격대:", ", ".join("%d원" % p for p in prices))
    print("시리즈:", ", ".join("%s %d" % (k, v) for k, v in sorted(series.items(), key=lambda x: -x[1])))
    print("품절 표기:", sum(1 for i in items if i["soldout"]), "개")
    print("\n%d/%d passed" % (len(items) and 0 or 0, 0) if False else "")
    print("%s" % ("모든 검사 통과" if not fails else "실패: " + ", ".join(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
