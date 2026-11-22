# 이케아 수납·선반 미리보기 (IKEA Storage Simulator)

칼락스·빌리·베스토·팍스 같은 이케아 수납칸의 **안쪽 치수**를 넣으면, 그 칸에 딱 맞는
이케아 수납 상자·바구니·서랍 정리함을 골라주는 정적 웹앱입니다.

- 라이브: https://coolkim011.github.io/ikea-storage-simulator/
- 데이터: 이케아 코리아(ikea.com/kr/ko) 제품 페이지에서 2026-11-22 수집 (218종)

## 기능

| 기능 | 설명 |
| --- | --- |
| 가구 프리셋 | 칼락스 1칸 · 빌리 80/40폭 · 베스토 1칸 · 팍스 50/100폭 · 이바르 80×30/80×50 · 트로파스트 프레임 |
| 맞춤 추천 | 칸에 들어가는 순서(여유 폭 기준)로 정렬, 시리즈 필터 + "들어가는 것만" 토글 + 제품명·제품번호 검색 |
| 3면 미리보기 | 앞에서 / 옆에서 / 위에서. 드래그 이동, 쌓기, 벽·이웃에 자석 스냅 |
| 편집 툴바 | 돌리기(가로↔세로) · 눕히기 · 앞뒤 2줄 · 제거, 전체 되돌리기 |
| 쇼핑 리스트 PNG | 제품명·시리즈·제품번호(xxx.xxx.xx)·수량·단가·소계·합계·칸 규격을 담은 고해상도 PNG(2280px) |
| 자동 저장 | localStorage 에 배치와 칸 규격 유지 |

## 구조

```
index.html
assets/styles.css     이케아 톤(오프화이트 #F7F7F5 · 차콜 #111 · 블루 #0058A3 · 옐로 #FFDB00)
assets/app.js         의존성 없는 바닐라 JS (배치 엔진 + 3면 렌더 + 캔버스 영수증)
data/items.json       수집 원본(JSON)
data/items.js         앱이 읽는 사본(window.IKEA_DATA)
scripts/collect_ikea.py  수집·검증 파이프라인(검색 API → 제품 페이지 치수/제품번호)
tests/validate_data.py   데이터 형식·규격 검증
tests/smoke_test.py      quickjs + DOM 셰임으로 앱 실제 실행 테스트
```

## 데이터 수집 방식

1. 이케아 코리아 공개 검색 API(`sik.search.blue.cdtapps.com`)로 후보 수집
2. 각 제품 페이지(PIP)의 **치수** 표(폭 / 깊이(길이) / 높이)를 파싱 — cm 로 모두 표기된 제품만 채택
3. 제품번호는 제품 URL 끝 8자리(`...-80526876` → `805.268.76`)로 확정. 페이지에 함께 실린
   다른 변형 번호를 잘못 집지 않도록 URL 기준으로만 판정
4. 수납 용기가 아닌 품목(수납 가구 세트, 휴지통, 후크, 묶음 상품 등)은 `scripts/collect_ikea.py` 의
   `DROP_TYPE` / `DROP_ID` 로 제외

```bash
python3 scripts/collect_ikea.py candidates   # 후보 수집
python3 scripts/collect_ikea.py details      # 제품 페이지 확인 → data/items.json + items.js
python3 tests/validate_data.py
python3 tests/smoke_test.py                  # pip install quickjs
```

이 도구는 이케아와 무관한 비공식 팬메이드 도구입니다. 규격·가격은 수집 시점 기준입니다.
