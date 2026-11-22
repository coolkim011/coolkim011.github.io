#!/usr/bin/env python3
"""다이소몰에서 수납 바구니 데이터를 다시 수집한다 (재현용 스크립트).

앱이 쓰는 data/baskets.json 을 만드는 파이프라인을 한 파일로 정리한 것입니다.
  1) 검색 API 로 후보 상품(pdNo) 수집
  2) 상품 상세 API 로 품명·가격·카테고리·재고 수집
  3) 상품 설명에서 품번과 '가로/세로/높이' 사이즈 표기를 읽어 규격이 확인되는 상품만 남김

실행: python3 scripts/collect_daiso.py [출력경로]
주의: 다이소몰 서버 상태/차단 정책에 따라 실패할 수 있습니다. 하루 수백 건 이상 연속 호출하면
      403 이 돌아올 수 있으니 간격을 두고 실행하세요. (2026-11-22 기준 96종 수집)
"""
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

SEARCH = "https://www.daisomall.co.kr/ssn/search/SearchGoods"
API = "https://fapi.daisomall.co.kr"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
HEAD = {"Content-Type": "application/json", "Origin": "https://www.daisomall.co.kr",
        "Referer": "https://www.daisomall.co.kr/", "User-Agent": UA}

QUERIES = ["수납바구니", "바구니", "팬트리", "브릭스", "메쉬 수납", "냉장고 수납",
           "리빙박스", "수납함", "정리함", "직사각 바구니", "수납 트레이", "주방 수납"]
KEEP_MIDDLE = {"바구니류", "수납정리함", "네트망", "주방수납정리"}
DIM_RE = re.compile(r"(\d{1,2}(?:\.\d)?)\s*[*xX×]\s*(\d{1,2}(?:\.\d)?)\s*[*xX×]\s*(\d{1,2}(?:\.\d)?)")
LBL_RE = re.compile(r"(가로|세로|높이|폭|깊이)\s*[:：]?\s*(?:약\s*)?(\d{1,3}(?:\.\d)?)")


def search(q, page=1, size=100):
    url = SEARCH + "?" + urllib.parse.urlencode({"searchTerm": q, "pageNum": page, "cntPerPage": size})
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://www.daisomall.co.kr/"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode())


def post(path, body):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode(), headers=HEAD, method="POST")
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode())


def plain(v):
    parts = []

    def walk(x):
        if isinstance(x, dict):
            for vv in x.values():
                walk(vv)
        elif isinstance(x, list):
            for vv in x:
                walk(vv)
        elif isinstance(x, str):
            t = html.unescape(x)
            if "<" in t:
                t = re.sub(r"<[^>]+>", " ", t)
            parts.append(t)

    walk(v)
    return re.sub(r"[ \t]+", " ", "\n".join(parts))


def labeled_dims(text):
    """상품 자체의 '사이즈' 구획에 가로/세로/높이 라벨이 붙어 있으면 그 값을 쓴다."""
    for m in re.finditer(r"(?:SIZE|사이즈)", text):
        seg = text[m.start(): m.start() + 260]
        got = {}
        for lab, num in LBL_RE.findall(seg):
            key = {"가로": "w", "폭": "w", "세로": "d", "깊이": "d", "높이": "h"}[lab]
            got.setdefault(key, float(num))
        if all(k in got for k in ("w", "d", "h")) and all(1 <= v <= 150 for v in got.values()):
            return [got["w"], got["d"], got["h"]], "label"


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else "data/baskets.json"
    cand = {}
    for q in QUERIES:
        for page in range(1, 5):
            try:
                res = search(q, page)
            except Exception as e:
                print("검색 실패", q, page, e)
                break
            doc = res["resultSet"]["result"][-1]
            docs = doc.get("resultDocuments") or []
            if not docs:
                break
            for it in docs:
                cand.setdefault(it["pdNo"], it)
            if page * 100 >= doc.get("totalSize", 0):
                break
            time.sleep(0.4)
        print(q, "→ 후보", len(cand), flush=True)

    keep = [c for c in cand.values()
            if c.get("exhMiddleCtgrNm") in KEEP_MIDDLE and not c["pdNo"].startswith("B")]

    def detail(c):
        pd = c["pdNo"]
        try:
            info = post("/pd/pdr/pdDtl/selPdDtlInfo", {"pdNo": pd})["data"]
            desc = post("/pd/pdr/pdDtl/selPdDtlDesc", {"pdNo": pd})
        except Exception as e:
            return None
        text = plain(desc)
        dims = labeled_dims(text)
        if not dims:
            return None
        code = re.search(r"품번\s*[:：]\s*([0-9A-Za-z\-]+)", text)
        if not code or info.get("grpPdYn") == "Y":
            return None
        ctgr = info.get("exhCtgr") or [{}]
        return {
            "id": code.group(1),
            "pd": pd,
            "name": re.sub(r"\s+", " ", info.get("exhPdNm") or ""),
            "price": info.get("pdPrc"),
            "w": dims[0][0], "d": dims[0][1], "h": dims[0][2],
            "cat": " / ".join(x for x in [ctgr[0].get("lctgrNm"), ctgr[0].get("mctgrNm"), ctgr[0].get("sctgrNm")] if x),
            "img": ("https://cdn.daisomall.co.kr" + info["imgUrl"]) if info.get("imgUrl") else None,
            "url": f"https://www.daisomall.co.kr/ds/pd/pdr/SCR_PDR_0001?pdNo={pd}",
            "soldout": 0 if info.get("sleStsCd") == "03" and (info.get("stckQy") or 0) > 0 else 1,
            "reviews": info.get("revwCnt") or 0,
            "src": "label",
        }

    items = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        for r in ex.map(detail, keep):
            if r:
                items.append(r)

    items.sort(key=lambda x: (-x["reviews"], x["price"], x["name"]))
    data = {
        "meta": {"title": "다이소 수납 바구니 규격 데이터", "source": "다이소몰 (daisomall.co.kr)",
                 "collectedAt": time.strftime("%Y-%m-%d"), "count": len(items)},
        "items": items,
    }
    json.dump(data, open(out_path, "w"), ensure_ascii=False, indent=1)
    print("저장", out_path, len(items), "종")


if __name__ == "__main__":
    main()
