/* 이케아 수납·선반 미리보기
   - 데이터: data/items.js (이케아 코리아에서 수집한 수납 상자·바구니 218종)
   - 의존성 없음. 정적 호스팅(GitHub Pages / 파일 열기)에서 그대로 동작. */
(function () {
  'use strict';

  var DATA = window.IKEA_DATA || { meta: {}, items: [] };
  var ITEMS = (DATA.items || []).slice();
  var BY_ID = {};
  ITEMS.forEach(function (it) { BY_ID[it.id] = it; });

  var STEP = 0.5;          // 배치 스냅 단위(cm)
  var SNAP = 1.4;          // 자석처럼 붙는 거리(cm)
  var STORAGE_KEY = 'ikea-storage-sim-v1';

  var PRESETS = {
    kallax1: { name: '칼락스 KALLAX 1칸', w: 33, d: 39, h: 33 },
    billy80: { name: '빌리 BILLY 80폭', w: 76, d: 26, h: 30 },
    billy40: { name: '빌리 BILLY 40폭', w: 36, d: 26, h: 30 },
    besta1:  { name: '베스토 BESTÅ 1칸', w: 56, d: 36, h: 38 },
    pax50:   { name: '팍스 PAX 50폭', w: 46, d: 58, h: 35 },
    pax100:  { name: '팍스 PAX 100폭', w: 96, d: 58, h: 35 },
    ivar30:  { name: '이바르 IVAR 80×30', w: 83, d: 30, h: 40 },
    ivar50:  { name: '이바르 IVAR 80×50', w: 83, d: 50, h: 40 },
    trofast: { name: '트로파스트 TROFAST 프레임', w: 42, d: 30, h: 36 }
  };

  // 시리즈 필터에서 먼저 보여줄 순서(데이터에 있는 것만 노출)
  var PINNED_SERIES = ['쿠기스', '드뢰나', '스쿠브', '삼라', '트로파스트', '바리에라',
                       '우프다테라', '칼락스', '소케르비트', '콤플레멘트'];

  var state = {
    shelf: { w: 33, d: 39, h: 33 },
    preset: 'kallax1',
    placed: [],            // { uid, id, x, y, row, rot, lay }
    sel: null,
    view: 'front',
    filter: 'all',
    query: '',
    onlyFit: true,
    history: []
  };

  /* ---------------- utils ---------------- */
  function $(id) { return document.getElementById(id); }
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  function uid() { return 'u' + Math.random().toString(36).slice(2, 9); }
  function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }
  function round(v) { return Math.round(v * 10) / 10; }
  function won(n) { return n.toLocaleString('ko-KR'); }
  function num(v) { var n = parseFloat(v); return isFinite(n) ? n : 0; }
  function fmt(v) { return (Math.round(v * 10) / 10).toString(); }

  var toastTimer = null;
  function toast(msg) {
    var t = $('toast');
    t.textContent = msg;
    t.hidden = false;
    requestAnimationFrame(function () { t.classList.add('show'); });
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      t.classList.remove('show');
      setTimeout(function () { t.hidden = true; }, 220);
    }, 1900);
  }

  /* ---------------- geometry ---------------- */
  function dimsOf(p) {
    var it = BY_ID[p.id];
    if (!it) return { w: 0, d: 0, h: 0 };
    var w = it.w, d = it.d, h = it.h, t;
    if (p.rot) { t = w; w = d; d = t; }
    if (p.lay) { t = h; h = d; d = t; }
    return { w: round(w), d: round(d), h: round(h) };
  }

  function overlaps(a, b) {
    return a.x < b.x + b.w - 0.01 && a.x + a.w > b.x + 0.01 &&
           a.y < b.y + b.h - 0.01 && a.y + a.h > b.y + 0.01;
  }

  function zRange(row, d) {
    return row === 0 ? [0, d] : [state.shelf.d - d, state.shelf.d];
  }

  function fitsAt(p, x, y, row, ignoreUid) {
    var S = state.shelf, dm = dimsOf(p);
    if (x < -0.01 || y < -0.01) return false;
    if (x + dm.w > S.w + 0.01) return false;
    if (y + dm.h > S.h + 0.01) return false;
    if (dm.d > S.d + 0.01) return false;
    var box = { x: x, y: y, w: dm.w, h: dm.h };
    var zr = zRange(row, dm.d);
    for (var i = 0; i < state.placed.length; i++) {
      var o = state.placed[i];
      if (o.uid === ignoreUid) continue;
      var od = dimsOf(o);
      var ob = { x: o.x, y: o.y, w: od.w, h: od.h };
      if (!overlaps(box, ob)) continue;
      if (o.row === row) return false;
      // 앞뒤 줄이 깊이에서 겹치면 실제로는 부딪힌다
      var oz = zRange(o.row, od.d);
      if (zr[0] < oz[1] - 0.01 && zr[1] > oz[0] + 0.01) return false;
    }
    return true;
  }

  /* 바닥이 아닌 높이에 놓을 때, 아래 수납함이 폭의 절반 이상을 받쳐주는지 */
  function supportRatio(p, x, y, row) {
    if (y <= 0.01) return 1;
    var dm = dimsOf(p);
    var L = x, R = x + dm.w, covered = 0, spans = [];
    for (var i = 0; i < state.placed.length; i++) {
      var o = state.placed[i];
      if (o.uid === p.uid || o.row !== row) continue;
      var od = dimsOf(o);
      if (Math.abs(o.y + od.h - y) > 0.6) continue;
      var a = Math.max(L, o.x), b = Math.min(R, o.x + od.w);
      if (b - a > 0.01) spans.push([a, b]);
    }
    spans.sort(function (p1, p2) { return p1[0] - p2[0]; });
    var cur = null;
    spans.forEach(function (sp) {
      if (!cur) { cur = sp.slice(); return; }
      if (sp[0] <= cur[1] + 0.01) cur[1] = Math.max(cur[1], sp[1]);
      else { covered += cur[1] - cur[0]; cur = sp.slice(); }
    });
    if (cur) covered += cur[1] - cur[0];
    return dm.w ? covered / dm.w : 0;
  }

  function orientations(it) {
    var list = [], seen = {};
    [[0, 0], [1, 0], [0, 1], [1, 1]].forEach(function (o) {
      var w = it.w, d = it.d, h = it.h, t;
      if (o[0]) { t = w; w = d; d = t; }
      if (o[1]) { t = h; h = d; d = t; }
      var key = w.toFixed(1) + '/' + d.toFixed(1) + '/' + h.toFixed(1);
      if (seen[key]) return;
      seen[key] = 1;
      list.push({ rot: o[0], lay: o[1], w: w, d: d, h: h });
    });
    return list;
  }

  /* 칸에 담을 자리를 찾는다: 바닥 → 쌓기, 앞줄 → 뒷줄 */
  function findSpot(it, ignoreUid) {
    var S = state.shelf;
    var orients = orientations(it).filter(function (o) {
      return o.w <= S.w + 0.01 && o.h <= S.h + 0.01 && o.d <= S.d + 0.01;
    });
    // 눕혀서 높이가 오히려 높아지는 방향은 자동 배치에서 쓰지 않는다(손으로 눕히기는 가능)
    var upright = orients.filter(function (o) { return o.h <= it.h + 0.01; });
    if (upright.length) orients = upright;
    if (!orients.length) return null;

    var rows = [0, 1];
    for (var r = 0; r < rows.length; r++) {
      var row = rows[r];
      var ys = [0];
      state.placed.forEach(function (p) {
        if (p.row !== row) return;
        var pd = dimsOf(p);
        ys.push(round(p.y + pd.h));
      });
      ys = ys.filter(function (v, i, a) { return v >= 0 && v <= S.h && a.indexOf(v) === i; })
             .sort(function (a, b) { return a - b; });

      for (var oi = 0; oi < orients.length; oi++) {
        var o = orients[oi];
        var probe = { id: it.id, rot: o.rot, lay: o.lay };
        for (var yi = 0; yi < ys.length; yi++) {
          var y = ys[yi];
          if (y + o.h > S.h + 0.01) continue;
          for (var x = 0; x + o.w <= S.w + 0.01; x += STEP) {
            if (!fitsAt(probe, x, y, row, ignoreUid)) continue;
            if (supportRatio(probe, x, y, row) < 0.5) continue;
            return { x: round(x), y: round(y), row: row, rot: o.rot, lay: o.lay };
          }
        }
      }
    }
    return null;
  }

  function pushHistory() {
    state.history.push(JSON.stringify(state.placed));
    if (state.history.length > 60) state.history.shift();
  }

  /* 칸 크기를 바꾼 뒤 겹친 수납함을 다시 자리 잡게 한다 */
  function repair() {
    var kept = [];
    state.placed.forEach(function (p) {
      var saved = state.placed;
      state.placed = kept;
      var ok = fitsAt(p, p.x, p.y, p.row, p.uid);
      if (ok) { kept.push(p); return; }
      var it = BY_ID[p.id];
      var spot = it ? findSpot(it) : null;
      if (spot) {
        p.x = spot.x; p.y = spot.y; p.row = spot.row; p.rot = spot.rot; p.lay = spot.lay;
        kept.push(p);
      }
      state.placed = saved;
    });
    state.placed = kept;
    if (state.sel && !kept.some(function (p) { return p.uid === state.sel; })) state.sel = null;
  }

  /* ---------------- metrics ---------------- */
  function metrics() {
    var S = state.shelf, maxEdge = [0, 0], maxDepth = 0, maxTop = 0, total = 0;
    state.placed.forEach(function (p) {
      var dm = dimsOf(p);
      total += (BY_ID[p.id] ? BY_ID[p.id].price : 0);
      if (p.y < 0.01) maxEdge[p.row] = Math.max(maxEdge[p.row], p.x + dm.w);
      maxDepth = Math.max(maxDepth, dm.d);
      maxTop = Math.max(maxTop, p.y + dm.h);
    });
    var twoRows = state.placed.some(function (p) { return p.row === 1; });
    return {
      widthLeft: Math.max(0, round(S.w - Math.max(maxEdge[0], maxEdge[1]))),
      depthLeft: round(twoRows ? 0 : S.d - maxDepth),
      count: state.placed.length,
      total: total,
      top: round(maxTop),
      heightLeft: Math.max(0, round(S.h - maxTop))
    };
  }

  /* ---------------- catalog ---------------- */
  function fitInfo(it) {
    var S = state.shelf, best = null;
    var orients = orientations(it).filter(function (o) { return o.h <= it.h + 0.01; });
    if (!orients.length) orients = orientations(it);
    orients.forEach(function (o) {
      if (o.w > S.w + 0.01 || o.h > S.h + 0.01 || o.d > S.d + 0.01) return;
      var score = (S.w - o.w) + (S.d - o.d) * 0.35 + (S.h - o.h) * 0.15;
      if (!best || score < best.score) {
        best = { score: score, leftW: S.w - o.w, leftD: S.d - o.d, leftH: S.h - o.h, rot: o.rot, lay: o.lay };
      }
    });
    return best;
  }

  function groupOf(it) {
    if (it.group === 'kitchen' || it.group === 'drawer') return 'kitchen';
    return it.group || 'box';
  }

  function buildFilters() {
    var counts = {};
    ITEMS.forEach(function (it) {
      if (!it.seriesKo) return;
      counts[it.seriesKo] = (counts[it.seriesKo] || 0) + 1;
    });
    var picked = [];
    PINNED_SERIES.forEach(function (s) { if (counts[s]) picked.push(s); });
    Object.keys(counts).sort(function (a, b) { return counts[b] - counts[a]; })
      .forEach(function (s) {
        if (picked.length >= 13) return;
        if (counts[s] < 4 || picked.indexOf(s) >= 0) return;
        picked.push(s);
      });

    var row = $('filters');
    row.textContent = '';
    var all = el('button', 'chip is-on', '전체');
    all.type = 'button';
    all.setAttribute('data-filter', 'all');
    row.appendChild(all);
    picked.forEach(function (s) {
      var b = el('button', 'chip', s);
      b.type = 'button';
      b.setAttribute('data-filter', 's:' + s);
      row.appendChild(b);
    });
    var k = el('button', 'chip', '주방·서랍');
    k.type = 'button';
    k.setAttribute('data-filter', 'zone:kitchen');
    row.appendChild(k);
  }

  function filteredItems() {
    var q = state.query.trim().toLowerCase().replace(/\s+/g, '');
    var list = ITEMS.filter(function (it) {
      if (state.filter.indexOf('s:') === 0) {
        if (it.seriesKo !== state.filter.slice(2)) return false;
      } else if (state.filter === 'zone:kitchen') {
        if (groupOf(it) !== 'kitchen') return false;
      }
      if (q) {
        var hay = (it.name + ' ' + (it.typeName || '') + ' ' + (it.seriesKo || '') + ' ' +
                   (it.series || '') + ' ' + it.id + ' ' + it.id.replace(/\./g, '') + ' ' +
                   (it.color || '')).toLowerCase().replace(/\s+/g, '');
        if (hay.indexOf(q) < 0) return false;
      }
      return true;
    });
    list.sort(function (a, b) {
      var fa = fitInfo(a), fb = fitInfo(b);
      if (!!fa !== !!fb) return fa ? -1 : 1;
      if (fa && fb && Math.abs(fa.score - fb.score) > 0.05) return fa.score - fb.score;
      return (b.reviews || 0) - (a.reviews || 0);
    });
    if (state.onlyFit) list = list.filter(function (it) { return !!fitInfo(it); });
    return list;
  }

  function thumb(it) {
    var box = el('a', 'p-thumb');
    box.href = it.url || '#';
    box.target = '_blank';
    box.rel = 'noopener noreferrer';
    box.title = '이케아 제품 페이지 열기';
    if (it.img) {
      var img = document.createElement('img');
      img.src = it.img;
      img.alt = it.name;
      img.loading = 'lazy';
      img.decoding = 'async';
      img.addEventListener('error', function () {
        img.remove();
        box.appendChild(el('span', 'ph', 'IKEA'));
      });
      box.appendChild(img);
    } else {
      box.appendChild(el('span', 'ph', 'IKEA'));
    }
    return box;
  }

  function renderCatalog() {
    var grid = $('cardGrid');
    var list = filteredItems();
    grid.textContent = '';

    var fits = list.filter(function (it) { return !!fitInfo(it); }).length;
    var S = state.shelf;
    $('resultSummary').innerHTML = '<b>' + list.length + '종</b> 표시 · 칸 ' +
      fmt(S.w) + ' × ' + fmt(S.d) + ' × ' + fmt(S.h) + 'cm 에 <b>' + fits + '종</b>이 들어가요';

    if (!list.length) {
      $('emptyResult').hidden = false;
      return;
    }
    $('emptyResult').hidden = true;

    var frag = document.createDocumentFragment();
    list.forEach(function (it) {
      var fit = fitInfo(it);
      var card = el('li', 'p-card' + (fit ? '' : ' noFit'));

      card.appendChild(thumb(it));

      var body = el('div', 'p-body');
      var top = el('div', 'p-top');
      var nameWrap = el('div', 'p-namewrap');
      nameWrap.appendChild(el('div', 'p-name', it.name));
      var sub = it.typeName || '';
      if (it.color) sub += (sub ? ' · ' : '') + it.color;
      nameWrap.appendChild(el('div', 'p-type', sub));
      top.appendChild(nameWrap);

      var badge = el('span', 'badge-fit');
      if (!fit) {
        badge.textContent = '칸보다 큼';
        badge.className = 'badge-fit bad';
      } else if (fit.leftW <= 1) {
        badge.textContent = '딱 맞음';
      } else if (fit.leftW <= 5) {
        badge.textContent = '여유 ' + fmt(fit.leftW) + 'cm';
        badge.className = 'badge-fit warn';
      } else {
        badge.textContent = '여유 ' + fmt(fit.leftW) + 'cm';
      }
      top.appendChild(badge);
      body.appendChild(top);

      var meta = el('div', 'p-meta');
      meta.appendChild(el('span', 'p-dims', fmt(it.w) + ' × ' + fmt(it.d) + ' × ' + fmt(it.h) + ' cm'));
      meta.appendChild(el('span', 'p-code', it.id));
      if (fit && (fit.rot || fit.lay)) {
        var how = fit.rot && fit.lay ? '돌려 눕혀서' : (fit.rot ? '돌려서' : '눕혀서');
        meta.appendChild(el('span', 'p-hint', '↻ ' + how + ' 담김'));
      }
      body.appendChild(meta);

      var foot = el('div', 'p-foot');
      foot.appendChild(el('div', 'p-price', won(it.price) + '원'));
      var btn = el('button', 'add-btn', fit ? '칸에 담기' : '자리 없음');
      btn.type = 'button';
      btn.disabled = !fit;
      btn.addEventListener('click', function () { addItem(it.id); });
      foot.appendChild(btn);
      body.appendChild(foot);

      card.appendChild(body);
      frag.appendChild(card);
    });
    grid.appendChild(frag);
  }

  /* ---------------- stage rendering ---------------- */
  var stageEl, shelfBox;

  function layout() {
    var st = stageEl;
    var W = st.clientWidth || 600;
    var S = state.shelf;
    var ratio = state.view === 'top' ? (S.d / S.w) : (S.h / S.w);
    var hpx = clamp(W * ratio, 170, 420);
    st.style.height = Math.round(hpx) + 'px';
    return { W: W, H: hpx };
  }

  function renderStage() {
    if (!stageEl) return;
    stageEl.setAttribute('data-view', state.view);
    var size = layout();
    var S = state.shelf;

    shelfBox.textContent = '';

    var px = size.W / S.w;
    var py = (size.H - 10) / (state.view === 'top' ? S.d : S.h);
    // 옆에서 보기는 깊이가 가로축이라, 실제 비율을 유지한 채 가운데에 놓는다
    var originX = state.view === 'side' ? Math.max(0, (size.W - S.d * px) / 2) : 0;
    var spanX = state.view === 'side' ? S.d * px : size.W;

    if (state.view !== 'top') {
      var base = el('div', 'shelf-base');
      base.style.bottom = '0px';
      base.style.left = originX + 'px';
      base.style.right = 'auto';
      base.style.width = spanX + 'px';
      shelfBox.appendChild(base);
      var l = el('div', 'shelf-side'); l.style.left = originX + 'px';
      var r = el('div', 'shelf-side right');
      r.style.right = 'auto'; r.style.left = (originX + spanX - 6) + 'px';
      shelfBox.appendChild(l); shelfBox.appendChild(r);
    }

    var order = state.placed.slice().sort(function (a, b) {
      if (a.row !== b.row) return b.row - a.row;
      return (a.y - b.y) || (a.x - b.x);
    });

    order.forEach(function (p) {
      var it = BY_ID[p.id];
      if (!it) return;
      var dm = dimsOf(p);
      var node = el('div', 'item' + (p.row === 1 ? ' is-back' : '') + (state.sel === p.uid ? ' is-sel' : ''));
      node.setAttribute('data-uid', p.uid);

      var left, top, width, height;
      if (state.view === 'front') {
        left = p.x * px;
        width = dm.w * px;
        height = dm.h * py;
        top = (size.H - 10) - (p.y + dm.h) * py;
      } else if (state.view === 'side') {
        var z = p.row === 0 ? 0 : Math.max(0, S.d - dm.d);
        left = originX + z * px;
        width = dm.d * px;
        height = dm.h * py;
        top = (size.H - 10) - (p.y + dm.h) * py;
      } else {
        left = p.x * px;
        width = dm.w * px;
        height = dm.d * py;
        top = (p.row === 0 ? 0 : Math.max(0, S.d - dm.d)) * py;
        node.style.zIndex = String(10 + Math.round(p.y * 2));
      }

      node.style.left = left + 'px';
      node.style.top = top + 'px';
      node.style.width = Math.max(6, width - 1) + 'px';
      node.style.height = Math.max(6, height - 1) + 'px';
      if (state.sel === p.uid) node.style.zIndex = '40';

      if (width > 46 && height > 30) {
        node.appendChild(el('span', 'it-name', it.seriesKo || it.series || it.name));
        if (state.view !== 'side' && height > 52) {
          node.appendChild(el('span', 'it-dims', fmt(dm.w) + '×' + fmt(dm.d) + '×' + fmt(dm.h)));
        }
      }
      if (p.row === 1 && width > 30 && height > 24) node.classList.add('is-dup');

      shelfBox.appendChild(node);
    });

    $('stageEmpty').hidden = state.placed.length > 0;
    updateStats();
    var mini = $('miniBar');
    if (mini) {
      var mm = metrics();
      mini.hidden = mm.count === 0 || !!state.sel;
      $('miniCount').textContent = String(mm.count);
      $('miniTotal').textContent = won(mm.total) + '원';
    }
    $('undoBtn').disabled = state.history.length === 0;
    $('clearBtn').disabled = state.placed.length === 0;
    $('receiptOpenBtn').disabled = state.placed.length === 0;
    $('stageNote').textContent = state.view === 'front'
      ? '끌어서 옮기고, 다른 수납함 위에 쌓아보세요.'
      : state.view === 'top'
        ? '위에서 끌어 좌우 · 앞뒤 줄을 바꿔보세요.'
        : '옆에서 깊이와 높이를 확인하세요.';
    syncToolbar();
  }

  function updateStats() {
    var m = metrics();
    $('statWidth').textContent = fmt(m.widthLeft);
    $('statDepth').textContent = fmt(m.depthLeft);
    $('statCount').textContent = String(m.count);
    $('statTotal').textContent = won(m.total);
    $('statTop').textContent = fmt(m.top);
    $('statLeft').textContent = fmt(m.heightLeft);
  }

  /* ---------------- actions ---------------- */
  function addItem(id) {
    var it = BY_ID[id];
    if (!it) return;
    var spot = findSpot(it);
    if (!spot) { toast('칸에 자리가 없어요. 다른 수납함을 빼보세요.'); return; }
    pushHistory();
    var p = { uid: uid(), id: id, x: spot.x, y: spot.y, row: spot.row, rot: spot.rot, lay: spot.lay };
    state.placed.push(p);
    state.sel = p.uid;
    save(); renderStage(); renderCatalog();
    toast(it.name + ' 담았어요');
  }

  function selected() {
    for (var i = 0; i < state.placed.length; i++) {
      if (state.placed[i].uid === state.sel) return state.placed[i];
    }
    return null;
  }

  function actRotate() {
    var p = selected(); if (!p) return;
    var trial = { id: p.id, rot: p.rot ? 0 : 1, lay: p.lay };
    var dm = dimsOf(trial);
    var x = clamp(p.x, 0, Math.max(0, state.shelf.w - dm.w));
    if (!fitsAt(trial, x, p.y, p.row, p.uid)) { toast('돌리면 자리가 부족해요'); return; }
    pushHistory();
    p.rot = trial.rot; p.x = round(x);
    save(); renderStage();
    toast(dm.w + ' × ' + dm.d + 'cm로 돌렸어요');
  }

  function actLay() {
    var p = selected(); if (!p) return;
    var trial = { id: p.id, rot: p.rot, lay: p.lay ? 0 : 1 };
    var dm = dimsOf(trial);
    if (dm.h >= dimsOf(p).h + 0.01) { toast('이미 가장 낮은 방향이에요'); return; }
    var x = clamp(p.x, 0, Math.max(0, state.shelf.w - dm.w));
    var y = clamp(p.y, 0, Math.max(0, state.shelf.h - dm.h));
    if (!fitsAt(trial, x, y, p.row, p.uid)) { toast('눕히면 자리가 부족해요'); return; }
    pushHistory();
    p.lay = trial.lay; p.x = round(x); p.y = round(y);
    save(); renderStage();
    toast('눕혀서 높이 ' + fmt(dm.h) + 'cm로 놓았어요');
  }

  function actDup() {
    var p = selected(); if (!p) return;
    var dm = dimsOf(p);
    var other = p.row === 0 ? 1 : 0;
    if (dm.d * 2 > state.shelf.d + 0.01) { toast('깊이가 부족해 앞뒤 2줄은 어려워요'); return; }
    var trial = { id: p.id, rot: p.rot, lay: p.lay };
    if (!fitsAt(trial, p.x, p.y, other, null)) { toast('반대쪽 줄에 자리가 없어요'); return; }
    pushHistory();
    state.placed.push({ uid: uid(), id: p.id, x: p.x, y: p.y, row: other, rot: p.rot, lay: p.lay });
    save(); renderStage(); renderCatalog();
    toast('앞뒤 2줄로 놓았어요');
  }

  function actRemove() {
    var p = selected(); if (!p) return;
    pushHistory();
    state.placed = state.placed.filter(function (o) { return o.uid !== p.uid; });
    state.sel = null;
    save(); renderStage(); renderCatalog();
  }

  function undo() {
    if (!state.history.length) return;
    state.placed = JSON.parse(state.history.pop());
    if (state.sel && !state.placed.some(function (p) { return p.uid === state.sel; })) state.sel = null;
    save(); renderStage(); renderCatalog();
  }

  function clearAll() {
    if (!state.placed.length) return;
    pushHistory();
    state.placed = [];
    state.sel = null;
    save(); renderStage(); renderCatalog();
    toast('칸을 비웠어요 · 되돌리기로 복구할 수 있어요');
  }

  function syncToolbar() {
    var bar = $('selToolbar');
    var p = selected();
    if (!p) { bar.hidden = true; return; }
    var it = BY_ID[p.id]; if (!it) { bar.hidden = true; return; }
    var dm = dimsOf(p);
    bar.hidden = false;
    $('selName').textContent = it.name;
    $('selDims').textContent = fmt(dm.w) + ' × ' + fmt(dm.d) + ' × ' + fmt(dm.h) + 'cm · ' + it.id;
  }

  /* ---------------- drag ---------------- */
  var drag = null;

  function onPointerDown(e) {
    var node = e.target.closest ? e.target.closest('.item') : null;
    if (!node) {
      if (state.sel) { state.sel = null; renderStage(); }
      return;
    }
    var id = node.getAttribute('data-uid'), p = null;
    state.placed.forEach(function (o) { if (o.uid === id) p = o; });
    if (!p) return;

    if (state.sel !== p.uid) {
      state.sel = p.uid;
      var prev = stageEl.querySelector('.item.is-sel');
      if (prev) prev.classList.remove('is-sel');
      node.classList.add('is-sel');
      syncToolbar();
    }

    var st = stageEl.getBoundingClientRect();
    var S = state.shelf;
    drag = {
      uid: p.uid,
      startX: e.clientX, startY: e.clientY,
      ox: p.x, oy: p.y, orow: p.row,
      px: st.width / S.w,
      py: (st.height - 10) / (state.view === 'top' ? S.d : S.h),
      moved: false,
      node: node,
      before: JSON.stringify(state.placed)
    };
    node.classList.add('dragging');
    try { node.setPointerCapture(e.pointerId); } catch (err) {}
  }

  function onPointerMove(e) {
    if (!drag) return;
    var p = null;
    state.placed.forEach(function (o) { if (o.uid === drag.uid) p = o; });
    if (!p) return;
    var dx = (e.clientX - drag.startX) / drag.px;
    var dy = (e.clientY - drag.startY) / drag.py;
    if (Math.abs(dx) > 0.2 || Math.abs(dy) > 0.2) drag.moved = true;
    if (!drag.moved) return;

    var dm = dimsOf(p);
    var S = state.shelf;

    if (state.view === 'front') {
      p.x = round(clamp(drag.ox + dx, 0, Math.max(0, S.w - dm.w)));
      p.y = round(clamp(drag.oy + dy, 0, Math.max(0, S.h - dm.h)));
    } else if (state.view === 'top') {
      p.x = round(clamp(drag.ox + dx, 0, Math.max(0, S.w - dm.w)));
      var centerZ = (drag.orow === 0 ? dm.d / 2 : S.d - dm.d / 2) - dy;
      p.row = centerZ > S.d / 2 ? 1 : 0;
    } else {
      p.y = round(clamp(drag.oy + dy, 0, Math.max(0, S.h - dm.h)));
    }
    paintDragging(p);
    if (e.cancelable) e.preventDefault();
  }

  function paintDragging(p) {
    var node = stageEl.querySelector('.item[data-uid="' + p.uid + '"]');
    if (!node) return;
    var S = state.shelf, dm = dimsOf(p);
    var st = stageEl.getBoundingClientRect();
    var px = st.width / S.w;
    var py = (st.height - 10) / (state.view === 'top' ? S.d : S.h);
    if (state.view === 'front') {
      node.style.left = (p.x * px) + 'px';
      node.style.top = ((st.height - 10) - (p.y + dm.h) * py) + 'px';
    } else if (state.view === 'top') {
      node.style.left = (p.x * px) + 'px';
      node.style.top = ((p.row === 0 ? 0 : Math.max(0, S.d - dm.d)) * py) + 'px';
    } else {
      node.style.top = ((st.height - 10) - (p.y + dm.h) * py) + 'px';
    }
  }

  function onPointerUp() {
    if (!drag) return;
    var d = drag;
    drag = null;
    var p = null;
    state.placed.forEach(function (o) { if (o.uid === d.uid) p = o; });
    if (d.node) d.node.classList.remove('dragging');
    if (!p) return;

    if (d.moved) {
      var S = state.shelf, dm = dimsOf(p);
      var xs = [0, S.w - dm.w], ys = [0, S.h - dm.h];
      state.placed.forEach(function (o) {
        if (o.uid === p.uid || o.row !== p.row) return;
        var od = dimsOf(o);
        xs.push(o.x + od.w, o.x - dm.w);
        ys.push(o.y + od.h, o.y - dm.h);
      });
      var bx = p.x, by = p.y;
      xs.forEach(function (v) { if (Math.abs(p.x - v) < SNAP && v >= -0.01) bx = v; });
      ys.forEach(function (v) { if (Math.abs(p.y - v) < SNAP && v >= -0.01) by = v; });
      p.x = round(clamp(bx, 0, Math.max(0, S.w - dm.w)));
      p.y = round(clamp(by, 0, Math.max(0, S.h - dm.h)));

      if (!fitsAt(p, p.x, p.y, p.row, p.uid) || supportRatio(p, p.x, p.y, p.row) < 0.5) {
        state.placed = JSON.parse(d.before);
        toast('여기엔 놓을 수 없어요');
      } else if (d.before !== JSON.stringify(state.placed)) {
        state.history.push(d.before);
        if (state.history.length > 60) state.history.shift();
      }
    }
    renderStage();
    save();
  }

  /* ---------------- shopping list (PNG) ---------------- */
  function receiptGroups() {
    var map = {}, order = [];
    state.placed.forEach(function (p) {
      var it = BY_ID[p.id];
      if (!it) return;
      if (!map[p.id]) { map[p.id] = { it: it, qty: 0 }; order.push(p.id); }
      map[p.id].qty += 1;
    });
    return order.map(function (id) { return map[id]; });
  }

  function presetName() {
    var p = PRESETS[state.preset];
    return p ? p.name : '직접 잰 수납칸';
  }

  function dashed(ctx, x1, y1, x2, y2, color) {
    ctx.save();
    ctx.strokeStyle = color || '#DCDCDC';
    ctx.lineWidth = 1.5;
    ctx.setLineDash([6, 6]);
    ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
    ctx.restore();
  }

  function wrap(ctx, text, maxWidth, maxLines) {
    var chars = String(text).split('');
    var lines = [], line = '';
    chars.forEach(function (ch) {
      var test = line + ch;
      if (ctx.measureText(test).width > maxWidth && line) {
        lines.push(line);
        line = ch;
      } else {
        line = test;
      }
    });
    if (line) lines.push(line);
    if (lines.length > maxLines) {
      lines = lines.slice(0, maxLines);
      lines[maxLines - 1] = lines[maxLines - 1].replace(/.$/, '…');
    }
    return lines;
  }

  function drawReceipt() {
    var cv = $('receiptCanvas');
    var ctx = cv.getContext('2d');
    var groups = receiptGroups();
    var S = state.shelf;
    var W = 760, PAD = 46;
    var headH = 250, rowH = 74, footH = 214;
    var H = headH + Math.max(1, groups.length) * rowH + footH;
    var SCALE = 3;   // 저장용 고해상도(2280px 폭)

    cv.width = W * SCALE;
    cv.height = H * SCALE;
    cv.style.aspectRatio = W + ' / ' + H;
    cv.style.width = '100%';
    cv.style.height = 'auto';
    ctx.setTransform(SCALE, 0, 0, SCALE, 0, 0);
    ctx.clearRect(0, 0, W, H);

    // 배경
    ctx.fillStyle = '#FFFFFF';
    ctx.fillRect(0, 0, W, H);
    ctx.strokeStyle = '#E6E6E6';
    ctx.lineWidth = 2;
    ctx.strokeRect(10, 10, W - 20, H - 20);

    // 이케아 블루 헤더 + 옐로 라인
    ctx.fillStyle = '#0058A3';
    ctx.fillRect(10, 10, W - 20, 78);
    ctx.fillStyle = '#FFDB00';
    ctx.fillRect(10, 88, W - 20, 9);

    ctx.fillStyle = '#FFFFFF';
    ctx.font = '800 26px "Helvetica Neue", Arial, sans-serif';
    ctx.fillText('IKEA', PAD, 60);
    ctx.textAlign = 'right';
    ctx.font = '700 12px "Helvetica Neue", Arial, sans-serif';
    ctx.fillStyle = '#BBD3E8';
    ctx.fillText('SHOPPING LIST', W - PAD, 56);
    ctx.textAlign = 'left';

    // 제목
    ctx.fillStyle = '#111111';
    ctx.font = '800 29px "Pretendard", "Apple SD Gothic Neo", "Noto Sans KR", sans-serif';
    ctx.fillText('이케아 수납 쇼핑 리스트', PAD, 140);

    var d = new Date();
    var dateStr = d.getFullYear() + '.' + String(d.getMonth() + 1).padStart(2, '0') + '.' +
                  String(d.getDate()).padStart(2, '0');
    ctx.font = '600 13.5px "Pretendard", "Apple SD Gothic Neo", sans-serif';
    ctx.fillStyle = '#666666';
    ctx.fillText(presetName() + '  ·  ' + fmt(S.w) + ' × ' + fmt(S.d) + ' × ' + fmt(S.h) + ' cm', PAD, 168);
    ctx.fillStyle = '#999999';
    ctx.font = '500 12.5px "Pretendard", "Apple SD Gothic Neo", sans-serif';
    ctx.fillText('단위: 안쪽 폭 × 깊이 × 높이(cm)   ·   ' + dateStr, PAD, 190);

    dashed(ctx, PAD, 210, W - PAD, 210);

    // 컬럼 헤더
    var y = 234;
    ctx.font = '700 11.5px "Pretendard", "Apple SD Gothic Neo", sans-serif';
    ctx.fillStyle = '#999999';
    ctx.fillText('제품명 / 제품번호', PAD, y);
    ctx.textAlign = 'right';
    ctx.fillText('수량 × 단가', W - PAD - 130, y);
    ctx.fillText('소계', W - PAD, y);
    ctx.textAlign = 'left';

    y += 14;
    ctx.strokeStyle = '#111111';
    ctx.lineWidth = 1.6;
    ctx.beginPath(); ctx.moveTo(PAD, y); ctx.lineTo(W - PAD, y); ctx.stroke();
    y += 30;

    groups.forEach(function (g, idx) {
      var it = g.it;
      var lines = wrap(ctx, it.name, W - PAD * 2 - 250, 1);
      ctx.fillStyle = '#111111';
      ctx.font = '800 16.5px "Pretendard", "Apple SD Gothic Neo", sans-serif';
      ctx.fillText(lines[0] || it.name, PAD, y);

      var sub = (it.typeName || '') + (it.color ? ' · ' + it.color : '');
      ctx.fillStyle = '#777777';
      ctx.font = '500 12px "Pretendard", "Apple SD Gothic Neo", sans-serif';
      ctx.fillText(sub, PAD, y + 20);

      ctx.fillStyle = '#0058A3';
      ctx.font = '600 12px ui-monospace, "SFMono-Regular", Menlo, monospace';
      ctx.fillText('제품번호 ' + it.id, PAD, y + 38);

      ctx.textAlign = 'right';
      ctx.fillStyle = '#555555';
      ctx.font = '600 13.5px "Pretendard", "Apple SD Gothic Neo", sans-serif';
      ctx.fillText(g.qty + ' × ' + won(it.price) + '원', W - PAD - 130, y + 2);
      ctx.fillStyle = '#111111';
      ctx.font = '800 16px "Pretendard", "Apple SD Gothic Neo", sans-serif';
      ctx.fillText(won(g.qty * it.price) + '원', W - PAD, y + 2);
      ctx.textAlign = 'left';

      if (idx < groups.length - 1) {
        ctx.strokeStyle = '#EFEFEF';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(PAD, y + rowH - 18); ctx.lineTo(W - PAD, y + rowH - 18); ctx.stroke();
      }
      y += rowH;
    });

    dashed(ctx, PAD, y - 8, W - PAD, y - 8);

    var total = 0, qty = 0;
    groups.forEach(function (g) { total += g.qty * g.it.price; qty += g.qty; });
    y += 40;

    ctx.fillStyle = '#666666';
    ctx.font = '600 13.5px "Pretendard", "Apple SD Gothic Neo", sans-serif';
    ctx.fillText('총 ' + qty + '개 · ' + groups.length + '종', PAD, y);

    ctx.textAlign = 'right';
    ctx.fillStyle = '#111111';
    ctx.font = '700 14px "Pretendard", "Apple SD Gothic Neo", sans-serif';
    ctx.fillText('합계', W - PAD - 210, y);
    ctx.font = '800 34px "Pretendard", "Apple SD Gothic Neo", sans-serif';
    ctx.fillText(won(total) + '원', W - PAD, y + 6);
    ctx.textAlign = 'left';

    // 푸터
    y += 62;
    ctx.strokeStyle = '#EFEFEF';
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(PAD, y - 26); ctx.lineTo(W - PAD, y - 26); ctx.stroke();

    ctx.fillStyle = '#999999';
    ctx.font = '500 11.5px "Pretendard", "Apple SD Gothic Neo", sans-serif';
    ctx.fillText('규격·가격은 이케아 코리아(ikea.com/kr/ko) 제품 페이지 기준 · 2026-11-22 수집', PAD, y);
    ctx.fillText('매장 실측과 1~2cm 차이가 있을 수 있어요. 구매 전 제품 페이지에서 확인하세요.', PAD, y + 18);
    ctx.fillStyle = '#BBBBBB';
    ctx.fillText('이케아 수납·선반 미리보기 · 비공식 팬메이드 도구', PAD, y + 36);

    // 옐로 스탬프
    ctx.save();
    ctx.translate(W - PAD - 40, H - 62);
    ctx.fillStyle = '#FFDB00';
    ctx.beginPath(); ctx.arc(0, 0, 34, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = '#0058A3';
    ctx.textAlign = 'center';
    ctx.font = '800 13px "Helvetica Neue", Arial, sans-serif';
    ctx.fillText('IKEA', 0, 1);
    ctx.font = '700 8px "Helvetica Neue", Arial, sans-serif';
    ctx.fillText('PLAN', 0, 13);
    ctx.restore();
    ctx.textAlign = 'left';

    return cv;
  }

  function openReceipt() {
    if (!state.placed.length) return;
    drawReceipt();
    $('receiptModal').hidden = false;
    document.body.style.overflow = 'hidden';
  }

  function downloadReceipt() {
    var cv = $('receiptCanvas');
    if (!cv.toBlob) { toast('이 브라우저에서는 저장이 어려워요. 길게 눌러 저장해 주세요.'); return; }
    cv.toBlob(function (blob) {
      if (!blob) return;
      var d = new Date();
      var stamp = d.getFullYear() + String(d.getMonth() + 1).padStart(2, '0') + String(d.getDate()).padStart(2, '0');
      var a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'ikea-shopping-list-' + stamp + '.png';
      document.body.appendChild(a);
      a.click();
      setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1500);
      toast('쇼핑 리스트 PNG를 저장했어요');
    }, 'image/png');
  }

  /* ---------------- persist ---------------- */
  function save() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        shelf: state.shelf, placed: state.placed, preset: state.preset
      }));
    } catch (e) {}
  }
  function load() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      var d = JSON.parse(raw);
      if (d && d.shelf && d.placed && Array.isArray(d.placed)) {
        if (d.shelf.w > 0 && d.shelf.d > 0 && d.shelf.h > 0) state.shelf = d.shelf;
        state.placed = d.placed.filter(function (p) { return BY_ID[p.id]; });
        if (d.preset) state.preset = d.preset;
      }
    } catch (e) {}
  }

  /* ---------------- shelf inputs ---------------- */
  function markPreset(key) {
    state.preset = key || null;
    document.querySelectorAll('[data-preset]').forEach(function (b) {
      if (b.getAttribute('data-preset') === state.preset) b.classList.add('is-on');
      else b.classList.remove('is-on');
    });
  }

  function readShelf() {
    var w = clamp(num($('shelfW').value) || 33, 10, 300);
    var d = clamp(num($('shelfD').value) || 39, 8, 150);
    var h = clamp(num($('shelfH').value) || 33, 8, 150);
    state.shelf = { w: w, d: d, h: h };
    $('shelfW').value = fmt(w);
    $('shelfD').value = fmt(d);
    $('shelfH').value = fmt(h);

    var before = state.placed.length;
    state.placed = state.placed.filter(function (p) {
      var dm = dimsOf(p);
      return dm.w <= w + 0.01 && dm.h <= h + 0.01 && dm.d <= d + 0.01;
    });
    if (state.placed.length < before) {
      toast('새 규격에 안 들어가는 수납함 ' + (before - state.placed.length) + '개를 뺐어요');
    }
    state.placed.forEach(function (p) {
      var dm = dimsOf(p);
      p.x = round(clamp(p.x, 0, Math.max(0, w - dm.w)));
      p.y = round(clamp(p.y, 0, Math.max(0, h - dm.h)));
    });
    repair();
    save(); renderStage(); renderCatalog();
  }

  /* ---------------- wiring ---------------- */
  function init() {
    stageEl = $('stage');
    shelfBox = $('shelfBox');

    load();
    $('shelfW').value = fmt(state.shelf.w);
    $('shelfD').value = fmt(state.shelf.d);
    $('shelfH').value = fmt(state.shelf.h);
    $('dataCount').textContent = String(ITEMS.length);
    markPreset(PRESETS[state.preset] ? state.preset : null);
    buildFilters();

    ['shelfW', 'shelfD', 'shelfH'].forEach(function (id) {
      var input = $(id);
      input.addEventListener('input', function () { markPreset(null); });
      input.addEventListener('change', function () { markPreset(null); readShelf(); });
      input.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') { markPreset(null); readShelf(); input.blur(); }
      });
    });

    document.querySelectorAll('[data-preset]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var key = btn.getAttribute('data-preset');
        var p = PRESETS[key];
        if (!p) return;
        $('shelfW').value = p.w;
        $('shelfD').value = p.d;
        $('shelfH').value = p.h;
        markPreset(key);
        readShelf();
        toast(p.name + ' 기준으로 맞췄어요');
      });
    });

    document.querySelectorAll('.tab').forEach(function (tab) {
      tab.addEventListener('click', function () {
        document.querySelectorAll('.tab').forEach(function (t) {
          t.classList.remove('is-on');
          t.setAttribute('aria-selected', 'false');
        });
        tab.classList.add('is-on');
        tab.setAttribute('aria-selected', 'true');
        state.view = tab.getAttribute('data-view');
        renderStage();
      });
    });

    $('filters').addEventListener('click', function (e) {
      var btn = e.target.closest ? e.target.closest('[data-filter]') : null;
      if (!btn) return;
      document.querySelectorAll('[data-filter]').forEach(function (b) { b.classList.remove('is-on'); });
      btn.classList.add('is-on');
      state.filter = btn.getAttribute('data-filter');
      renderCatalog();
    });

    var searchTimer = null;
    $('searchInput').addEventListener('input', function (e) {
      clearTimeout(searchTimer);
      var v = e.target.value;
      searchTimer = setTimeout(function () { state.query = v; renderCatalog(); }, 120);
    });

    $('onlyFit').addEventListener('change', function (e) {
      state.onlyFit = e.target.checked;
      renderCatalog();
    });

    $('undoBtn').addEventListener('click', undo);
    $('clearBtn').addEventListener('click', clearAll);
    $('receiptOpenBtn').addEventListener('click', openReceipt);
    if ($('miniPreview')) {
      $('miniPreview').addEventListener('click', function () {
        var card = document.querySelector('.preview-card');
        if (card && card.scrollIntoView) card.scrollIntoView({ behavior: 'smooth', block: 'start' });
        else if (card) window.scrollTo(0, card.offsetTop || 0);
      });
      $('miniReceipt').addEventListener('click', openReceipt);
    }
    $('downloadBtn').addEventListener('click', downloadReceipt);

    $('selToolbar').addEventListener('click', function (e) {
      var btn = e.target.closest ? e.target.closest('[data-act]') : null;
      if (!btn) return;
      var act = btn.getAttribute('data-act');
      if (act === 'rotate') actRotate();
      else if (act === 'lay') actLay();
      else if (act === 'dup') actDup();
      else if (act === 'remove') actRemove();
      else if (act === 'close') { state.sel = null; renderStage(); }
    });

    document.querySelectorAll('[data-close]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var id = btn.getAttribute('data-close');
        $(id).hidden = true;
        document.body.style.overflow = '';
      });
    });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        var open = document.querySelector('.modal:not([hidden])');
        if (open) { open.hidden = true; document.body.style.overflow = ''; return; }
        if (state.sel) { state.sel = null; renderStage(); }
      }
      var tag = (e.target && e.target.tagName || '').toLowerCase();
      if (tag === 'input' || tag === 'textarea' || tag === 'select' || (e.target && e.target.isContentEditable)) return;
      var p = selected();
      if (!p) return;
      var step = e.shiftKey ? 5 : STEP;
      var dm = dimsOf(p);
      var handled = true, px0 = p.x, py0 = p.y, before = JSON.stringify(state.placed);
      if (e.key === 'ArrowLeft') p.x = clamp(p.x - step, 0, Math.max(0, state.shelf.w - dm.w));
      else if (e.key === 'ArrowRight') p.x = clamp(p.x + step, 0, Math.max(0, state.shelf.w - dm.w));
      else if (e.key === 'ArrowUp') p.y = clamp(p.y + step, 0, Math.max(0, state.shelf.h - dm.h));
      else if (e.key === 'ArrowDown') p.y = clamp(p.y - step, 0, Math.max(0, state.shelf.h - dm.h));
      else if (e.key === 'Delete' || e.key === 'Backspace') { actRemove(); handled = true; }
      else handled = false;
      if (handled) {
        e.preventDefault();
        if ((p.x !== px0 || p.y !== py0) &&
            (!fitsAt(p, p.x, p.y, p.row, p.uid) || supportRatio(p, p.x, p.y, p.row) < 0.5)) {
          p.x = px0; p.y = py0;
          toast('그쪽엔 놓을 수 없어요');
        } else if (p.x !== px0 || p.y !== py0) {
          state.history.push(before);
          if (state.history.length > 60) state.history.shift();
        }
        renderStage();
        save();
      }
    });

    $('openAbout').addEventListener('click', function () {
      var body = $('aboutBody');
      body.innerHTML = '';
      var p1 = el('p');
      p1.innerHTML = '이 시뮬레이터의 수납함 <b>' + ITEMS.length + '종</b>은 <b>이케아 코리아(ikea.com/kr/ko)</b>에서 ' +
        '2026년 11월 22일에 수집한 실제 판매 제품입니다. 제품명·제품번호(예: 805.268.76)·가격·색상은 제품 페이지와 같고, ' +
        '규격은 제품 페이지 <b>치수</b> 항목의 폭 / 깊이(길이) / 높이 값을 그대로 썼습니다.';
      body.appendChild(p1);

      var p2 = el('p');
      p2.innerHTML = '수납 용기가 아닌 제품(수납 가구 세트, 휴지통, 걸이·후크, 트레이 묶음 등)과 치수 표기가 없는 ' +
        '제품은 추천에서 뺐습니다. 가격과 재고는 수집 시점 기준이라 지금과 다를 수 있어요.';
      body.appendChild(p2);

      var ul = el('ul');
      ['수집: 이케아 코리아 검색 + 제품 상세 페이지', '규격 단위: cm (가로 × 깊이 × 높이)',
       '제품번호: 제품 URL 8자리 (80526876 → 805.268.76)',
       '가구 프리셋: 칼락스·빌리·베스토·팍스·이바르·트로파스트 안쪽 치수',
       '수집일: 2026-11-22'].forEach(function (t) { ul.appendChild(el('li', null, t)); });
      body.appendChild(ul);

      var p3 = el('p');
      p3.innerHTML = '이 도구는 이케아와 무관한 팬메이드 도구예요. 매장에서 실제로 넣어보면 1~2cm 차이가 날 수 있으니, ' +
        '구매 전 <b>제품 페이지</b>에서 한 번 더 확인해 주세요.';
      body.appendChild(p3);
      $('aboutModal').hidden = false;
      document.body.style.overflow = 'hidden';
    });

    stageEl.addEventListener('pointerdown', onPointerDown);
    window.addEventListener('pointermove', onPointerMove, { passive: false });
    window.addEventListener('pointerup', onPointerUp);
    window.addEventListener('pointercancel', onPointerUp);
    window.addEventListener('resize', function () { renderStage(); });

    renderStage();
    renderCatalog();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
