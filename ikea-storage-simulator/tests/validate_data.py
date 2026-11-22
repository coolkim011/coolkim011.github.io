#!/usr/bin/env python3
"""데이터 검증: data/items.json / items.js 가 이케아 코리아에서 수집한 실측 값인지 형태를 확인한다.

실행: python3 tests/validate_data.py
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_JSON = os.path.join(ROOT, "data", "items.json")
DATA_JS = os.path.join(ROOT, "data", "items.js")

fails = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + (("  " + str(detail)) if detail else ""))
    if not cond:
        fails.append(name)


def main():
    data = json.load(open(DATA_JSON, encoding="utf-8"))
    items = data["items"]
    meta = data["meta"]

    check("상품 수 50종 이상", len(items) >= 50, len(items))
    check("meta.count 일치", meta.get("count") == len(items), meta.get("count"))
    check("수집 출처 표기", "ikea.com" in meta.get("source", ""), meta.get("source"))

    ids = [i["id"] for i in items]
    check("제품번호 중복 없음", len(ids) == len(set(ids)))

    bad_code = [i["id"] for i in items if not re.fullmatch(r"\d{3}\.\d{3}\.\d{2}", str(i["id"]))]
    check("제품번호 형식(xxx.xxx.xx)", not bad_code, bad_code[:5])

    bad_art = [i["id"] for i in items if i.get("artNo") != i["id"].replace(".", "")]
    check("artNo = 제품번호 8자리", not bad_art, bad_art[:5])

    bad_num = []
    for i in items:
        for k in ("w", "d", "h"):
            v = i.get(k)
            if not isinstance(v, (int, float)) or v != v or v <= 0:
                bad_num.append((i["id"], k, v))
    check("규격 값 유효(양수·NaN 없음)", not bad_num, bad_num[:5])

    out_range = [i["id"] for i in items
                 if not (1 <= i["w"] <= 200 and 1 <= i["d"] <= 200 and 1 <= i["h"] <= 200)]
    check("규격 범위(1~200cm)", not out_range, out_range[:5])

    bad_price = [i["id"] for i in items if not isinstance(i["price"], int) or i["price"] <= 0]
    check("가격 유효", not bad_price, bad_price[:5])

    bad_url = [i["id"] for i in items
               if not str(i.get("url", "")).startswith("https://www.ikea.com/kr/ko/p/")
               or i["id"].replace(".", "") not in str(i.get("url", ""))]
    check("제품 URL에 제품번호 포함", not bad_url, bad_url[:5])

    bad_img = [i["id"] for i in items
               if not str(i.get("img", "")).startswith("https://www.ikea.com/kr/ko/images/products/")]
    check("이미지 URL 형식", not bad_img, bad_img[:5])

    no_name = [i["id"] for i in items if not i.get("name") or not i.get("typeName")]
    check("품명·유형 존재", not no_name, no_name[:5])

    no_series = [i["id"] for i in items if not i.get("series") or not i.get("seriesKo")]
    check("시리즈(스웨덴어·한글) 존재", not no_series, no_series[:5])

    bad_group = sorted({i.get("group") for i in items} - {"box", "drawer", "kitchen", "etc"})
    check("그룹 값 유효", not bad_group, bad_group)

    check("규격 출처 표기", all(i.get("src") == "pip" for i in items))

    # 대표 제품 교차 확인(규격·제품번호가 널리 알려진 값과 같은지)
    BY = {i["id"]: i for i in items}
    samples = [
        ("805.268.76", (32, 32, 32)),   # KUGGIS 쿠기스 수납상자+뚜껑 32x32x32
        ("702.628.28", (33, 38, 33)),   # DRÖNA 드뢰나 수납함 33x38x33
        ("901.809.40", (39, 28, 28)),   # SAMLA 삼라 수납함 39x28x28
        ("105.820.88", (42, 30, 36)),   # TROFAST 트로파스트 수납상자 42x30x36
    ]
    miss = [s for s in samples if s[0] not in BY]
    check("대표 제품 존재", not miss, [s[0] for s in miss])
    wrong = [s[0] for s in samples if s[0] in BY and
             tuple(BY[s[0]][k] for k in ("w", "d", "h")) != s[1]]
    check("대표 제품 규격 일치", not wrong, wrong)

    # JS 파일이 JSON 과 같은 데이터인지
    js = open(DATA_JS, encoding="utf-8").read()
    m = re.search(r"window\.IKEA_DATA\s*=\s*(\{.*\});\s*$", js, re.S)
    check("items.js 형식", bool(m))
    if m:
        check("items.js == items.json", json.loads(m.group(1)) == data)

    # 요약
    series = {}
    for i in items:
        series[i["seriesKo"]] = series.get(i["seriesKo"], 0) + 1
    prices = sorted(i["price"] for i in items)
    print("\n시리즈 %d종 · 상위: %s" % (
        len(series), ", ".join("%s %d" % (k, v) for k, v in
                               sorted(series.items(), key=lambda x: -x[1])[:12])))
    print("가격대: %d원 ~ %d원 (중앙값 %d원)" % (prices[0], prices[-1], prices[len(prices) // 2]))
    print("그룹:", {g: sum(1 for i in items if i["group"] == g) for g in ("box", "drawer", "kitchen", "etc")})
    print("%s" % ("모든 검사 통과" if not fails else "실패: " + ", ".join(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
