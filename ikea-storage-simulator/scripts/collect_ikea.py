#!/usr/bin/env python3
"""이케아 코리아(ikea.com/kr/ko)에서 수납 상자·바구니·서랍 정리함 데이터를 수집한다.

파이프라인
  1) 공개 검색 API(sik.search.blue.cdtapps.com)로 후보 제품 수집
  2) 제품 페이지(PIP)에서 '치수' 항목(폭 / 깊이(길이) / 높이)과 제품번호(예: 805.268.76) 확인
  3) 폭·깊이·높이가 모두 cm 로 표기된 제품만 남긴다

실행
  python3 scripts/collect_ikea.py candidates          # 후보만 모아 tmp/candidates.json
  python3 scripts/collect_ikea.py details             # 후보 → data/items.json
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
API = "https://sik.search.blue.cdtapps.com/kr/ko/search-result-page"
API_VERSION = "20260727"   # ikea.com/kr/ko/product-lists/v3/serp-main-*.js 의 v 값
PIP = "https://www.ikea.com/kr/ko/p/"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(os.path.dirname(ROOT), "..", "tmp")
CAND = os.path.join(TMP, "ikea_candidates.json")
OUT = os.path.join(ROOT, "data", "items.json")

QUERIES = [
    # 일반 수납
    "수납상자", "수납함", "수납바구니", "바구니", "정리함", "수납박스", "수납 트레이",
    "서랍 정리", "서랍 인서트", "옷장 정리", "책장 수납", "장난감 정리", "신발 정리",
    "욕실 수납", "빨래 바구니", "사무실 정리", "케이블 정리", "서류 정리",
    # 주방
    "주방 수납", "주방 정리", "냉장고 정리", "팬트리", "양념 정리", "식기 정리",
    # 시리즈 (이케아에서 흔히 쓰는 수납 시리즈)
    "KUGGIS", "DRÖNA", "SKUBB", "SAMLA", "TROFAST", "VARIERA", "TJENA", "SOCKERBIT",
    "NOJIG", "KLÄMTARE", "UPPDATERA", "RAGGISAR", "PÄRKLA", "FJÄDERHARV", "DRÖNJÖNS",
    "KVISSLE", "GLIS", "PAPPIS", "MOPPE", "HELMER", "ALEX", "LACK", "BESTÅ", "KALLAX",
    "BILLY", "PAX", "IVAR", "NORDLI", "BRIMNES", "SMÄCKER", "SUNNERSTA", "FINTORP",
    "GODISHUS", "HIMMELSÖ", "SVALNÄS", "RISATORP", "VATTENKRASSE", "KRUSNING",
]

# 수납 용기/정리 도구로 볼 수 있는 분류만 남긴다(책장·서랍장 같은 가구 프레임은 제외)
KEEP_FILTER = {
    "boxes or baskets", "drawer and cabinet interiors", "kitchen interiors",
    "trays", "storage combinations", "laundry accessories", "bathroom accessories",
    "organisation", "baskets",
}
DROP_TYPE_WORDS = (
    "선반", "책장", "수납장", "서랍장", "옷장", "장식장", "프레임", "도어", "문짝",
    "유리 선반", "선반 유닛", "카트", "행거", "스툴", "의자", "테이블", "침대",
    "커튼", "조명", "전구", "러그", "매트", "쿠션", "이불", "베개",
)
SIZE_RE = re.compile(r"^(\d{1,3}(?:\.\d)?)\s*cm$")


def _get(url, timeout=40, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.2 + i)
    raise last


def search(q, size=100):
    url = API + "?" + urllib.parse.urlencode(
        {"q": q, "size": size, "c": "sr", "v": API_VERSION, "types": "PRODUCT"})
    return json.loads(_get(url))


def collect_candidates():
    seen = {}
    for q in QUERIES:
        try:
            d = search(q)
        except Exception as e:  # noqa: BLE001
            print("검색 실패", q, e, flush=True)
            continue
        items = d["searchResultPage"]["products"]["main"]["items"]
        for it in items:
            p = it.get("product") or {}
            pid = p.get("id")
            if not pid or pid in seen:
                continue
            seen[pid] = p
        print("%-14s +%3d  누적 %d" % (q, len(items), len(seen)), flush=True)
        time.sleep(0.35)

    keep = []
    for p in seen.values():
        fc = (p.get("filterClass") or "").strip()
        tn = p.get("typeName") or ""
        if fc and fc not in KEEP_FILTER:
            continue
        if any(w in tn for w in DROP_TYPE_WORDS):
            continue
        keep.append(p)

    os.makedirs(TMP, exist_ok=True)
    json.dump(keep, open(CAND, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("후보 %d개 / %d개 저장 → %s" % (len(keep), len(seen), CAND), flush=True)


MEAS_RE = re.compile(
    r'pipf-measurements-tab__measurement-name">([^<]+)</span>'
    r'<span class="pipf-measurements-tab__measurement-value">([^<]+)</span>')
ART_RE = re.compile(r'"articleNumber":\{"label":"[^"]*","value":"(\d{3}\.\d{3}\.\d{2})"\}')
PRICE_RE = re.compile(r'"salesPrice":\{"currencyCode":"KRW","numeral":([0-9.]+)')


def fetch_detail(p):
    pid = p.get("id")
    pip_url = p.get("pipUrl") or ""
    if not pip_url:
        return None
    try:
        html = _get(pip_url)
    except Exception as e:  # noqa: BLE001
        return {"id": pid, "err": "fetch %s" % e}
    pairs = MEAS_RE.findall(html)
    got = {}
    for label, val in pairs:
        m = SIZE_RE.match(val.strip())
        if not m:
            continue
        v = float(m.group(1))
        if label.strip() == "폭":
            got.setdefault("w", v)
        elif label.strip() in ("길이", "깊이", "세로"):
            got.setdefault("d", v)
        elif label.strip() == "높이":
            got.setdefault("h", v)
    if not all(k in got for k in ("w", "d", "h")):
        return {"id": pid, "err": "dims %s" % got, "pairs": pairs[:8]}

    # 제품번호는 제품 URL 끝 8자리(예: ...-80526876 → 805.268.76)를 쓴다.
    # 페이지에는 변형 제품의 번호도 함께 실려 있어 '첫 번째 번호'를 쓰면 다른 변형이 잡힌다.
    url_no = re.search(r"-s?(\d{8})/?$", pip_url)
    if not url_no:
        return {"id": pid, "err": "url no"}
    digits = url_no.group(1)
    art_fmt = "%s.%s.%s" % (digits[0:3], digits[3:6], digits[6:8])
    if art_fmt not in html:
        return {"id": pid, "err": "article no missing in page"}
    art_no = art_fmt

    price = p.get("salesPrice", {}).get("numeral")
    if price is None:
        m = PRICE_RE.search(html)
        price = float(m.group(1)) if m else None
    if not price:
        return {"id": pid, "err": "price"}

    name = re.sub(r"\s+", " ", p.get("name") or "").strip()
    parts = name.split(" ")
    series_sv = parts[0] if parts else ""
    series_ko = parts[1] if len(parts) > 1 and re.match(r"^[가-힣]", parts[1]) else ""
    imgs = p.get("allProductImage") or []
    main_img = p.get("mainImageUrl")
    if not main_img:
        for im in imgs:
            if im.get("type") == "MAIN_PRODUCT_IMAGE":
                main_img = im.get("url")
                break
    cats = [c.get("name") for c in (p.get("categoryPath") or [])]
    return {
        "id": art_no,
        "artNo": art_no.replace(".", ""),
        "name": name,
        "typeName": p.get("typeName") or "",
        "series": series_sv,
        "seriesKo": series_ko,
        "w": got["w"], "d": got["d"], "h": got["h"],
        "price": int(round(price)),
        "img": main_img or "",
        "url": pip_url,
        "cat": " / ".join([c for c in cats if c]),
        "filterClass": p.get("filterClass") or "",
        "color": ((p.get("colors") or [{}])[0].get("name") or ""),
        "rating": p.get("ratingValue") or 0,
        "reviews": p.get("ratingCount") or 0,
        "ref": p.get("itemMeasureReferenceText") or "",
        "src": "pip",
    }


def collect_details():
    cand = json.load(open(CAND, encoding="utf-8"))
    print("후보", len(cand))
    good, bad = [], []
    with ThreadPoolExecutor(max_workers=5) as ex:
        for i, r in enumerate(ex.map(fetch_detail, cand)):
            if r and "err" not in r:
                good.append(r)
            elif r:
                bad.append(r)
            if (i + 1) % 40 == 0:
                print("  %d/%d  성공 %d" % (i + 1, len(cand), len(good)), flush=True)

    # 같은 제품번호 중복 제거
    byid = {}
    for it in good:
        byid.setdefault(it["id"], it)
    items = list(byid.values())
    # 규격이 비정상인 값 제외
    items = [i for i in items if all(1 <= i[k] <= 200 for k in ("w", "d", "h"))]
    items.sort(key=lambda x: (-x["reviews"], x["series"], x["price"]))
    items, dropped = curate(items)

    data = {
        "meta": {
            "title": "이케아 코리아 수납 상자·바구니 규격 데이터",
            "source": "이케아 코리아 (ikea.com/kr/ko)",
            "collectedAt": time.strftime("%Y-%m-%d"),
            "count": len(items),
            "apiVersion": API_VERSION,
        },
        "items": items,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(data, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    errs = {}
    for b in bad:
        k = re.sub(r"[-0-9.]", "", str(b.get("err")))[:40]
        errs[k] = errs.get(k, 0) + 1
    write_js(data)
    print("큐레이션 제외", len(dropped), "종")
    for d0 in dropped:
        print("   -", d0[0], d0[1], "→", d0[2])
    print("저장", OUT, len(items), "종 / 제외", len(bad))
    print("제외 사유:", errs)



# ---- 큐레이션 ---------------------------------------------------------------
# 수납 '용기'가 아니라 가구·부속·도구인 품목은 뺀다(규격은 맞지만 선반 배치 대상이 아니다).
DROP_TYPE = {
    "휴지통", "터치식휴지통", "분리수거함+뚜껑", "세탁망", "건조대집게24",
    "키친타월꽂이", "조리도구랙", "칼걸이", "식기도구 가방", "보관용기 겸용 자석후크",
    "인출식내부부속품", "주방 조리대 정리용품", "싱크대 하단 정리용품", "티슈케이스",
    "흡착식바구니",
}
DROP_ID = {
    "704.540.02": "흡착식 바구니(벽 부착)",
    "805.279.08": "자석 후크",
    "203.812.54": "흡착식 바구니(벽 부착)",
    "696.127.24": "수납 가구 조합",
    "692.971.31": "수납 가구 조합",
    "892.974.89": "수납 가구 조합",
    "392.971.42": "수납 가구 조합",
    "091.873.81": "수납 가구 조합",
    "896.123.65": "수납 가구 조합",
    "793.026.79": "수납 가구 조합",
    "605.741.75": "이동식 수납 유닛",
    "005.371.81": "수납 가구 조합",
    "796.068.74": "수납 가구 조합",
    "196.019.83": "수납 가구 조합",
    "696.131.20": "수납 가구 조합",
    "296.131.36": "수납 가구 조합",
    "996.131.09": "수납 가구 조합",
    "196.127.26": "수납 가구 조합",
    "596.127.29": "수납 가구 조합",
}

GROUP = {
    "boxes or baskets": "box",
    "storage combinations": "box",
    "drawer and cabinet interiors": "drawer",
    "trays": "drawer",
    "kitchen interiors": "kitchen",
    "laundry accessories": "etc",
}


def curate(items):
    kept, dropped = [], []
    for it in items:
        tn = it.get("typeName") or ""
        if it["id"] in DROP_ID:
            dropped.append((it["id"], it["name"], DROP_ID[it["id"]]))
            continue
        if tn in DROP_TYPE:
            dropped.append((it["id"], it["name"], tn))
            continue
        if re.search(r"\d+종$", tn):
            dropped.append((it["id"], it["name"], "묶음 상품 " + tn))
            continue
        if it["filterClass"] == "storage combinations" and "인서트" not in tn:
            dropped.append((it["id"], it["name"], "수납 가구 조합"))
            continue
        it["group"] = GROUP.get(it["filterClass"], "box")
        kept.append(it)
    return kept, dropped


def write_js(data):
    js_path = os.path.join(ROOT, "data", "items.js")
    body = json.dumps(data, ensure_ascii=False, indent=1)
    with open(js_path, "w", encoding="utf-8") as f:
        f.write("/* 이케아 코리아(ikea.com/kr/ko)에서 %s 수집한 실데이터. "
                "scripts/collect_ikea.py 로 재생성할 수 있습니다. */\n" % data["meta"]["collectedAt"])
        f.write("window.IKEA_DATA = " + body + ";\n")
    print("저장", js_path)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd in ("candidates", "all"):
        collect_candidates()
    if cmd in ("details", "all"):
        collect_details()
