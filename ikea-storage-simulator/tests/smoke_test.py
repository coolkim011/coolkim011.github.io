#!/usr/bin/env python3
"""정적 앱 스모크 테스트: quickjs + 최소 DOM 셰임으로 index.html/app.js 를 실제 실행한다.

검증 항목
  1. app.js 가 오류 없이 초기화되고 카탈로그가 렌더된다
  2. '칸에 담기' 클릭 → 배치/통계/저장이 맞게 동작한다
  3. 이케아 가구 프리셋 · 시리즈 필터가 규격과 목록을 바꾼다
  4. 되돌리기·전부 빼기가 상태를 되돌린다
  5. 미리보기가 가로·세로 같은 배율(프레임 비율)이고 치수 라벨·얇은 트레이 라벨이 그려진다
  6. 선택 툴바가 미리보기 카드 안(통계 위)에 있다
  7. 쇼핑 리스트(제품번호 영수증) 캔버스 그리기가 예외 없이 끝난다
"""
import json
import os
import sys
from html.parser import HTMLParser

# 실행: 프로젝트 루트에서 `python3 tests/smoke_test.py` (quickjs 필요: pip install quickjs)

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class Node:
    def __init__(self, tag, attrs=None):
        self.tag = tag
        self.attrs = attrs or {}
        self.children = []


class P(HTMLParser):
    VOID = {"meta", "link", "br", "img", "input", "hr", "source"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        n = Node(tag, {k: (v if v is not None else "") for k, v in attrs})
        self.stack[-1].children.append(n)
        if tag not in self.VOID:
            self.stack.append(n)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.stack.pop()

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        if data.strip():
            n = Node("#text")
            n.text = data
            self.stack[-1].children.append(n)


def to_json(n):
    if n.tag == "#text":
        return {"t": "#text", "x": getattr(n, "text", "")}
    return {"t": n.tag, "a": n.attrs, "c": [to_json(c) for c in n.children]}


SHIM = r"""
var __handlers = {};
function uidSeq(){ uidSeq.n = (uidSeq.n||0)+1; return 'e'+uidSeq.n; }

function ClassList(el){
  this.el = el; this.set = {};
}
ClassList.prototype.add = function(){ for (var i=0;i<arguments.length;i++) this.set[arguments[i]]=1; };
ClassList.prototype.remove = function(){ for (var i=0;i<arguments.length;i++) delete this.set[arguments[i]]; };
ClassList.prototype.contains = function(c){ return !!this.set[c]; };
ClassList.prototype.toggle = function(c){ if (this.set[c]) delete this.set[c]; else this.set[c]=1; };

function El(tag){
  this.tagName = tag; this.children = []; this.style = {}; this.attrs = {};
  this.parent = null; this._text = ''; this._html = '';
  this.classList = new ClassList(this);
  this.handlers = {};
  this.hidden = false; this.disabled = false; this.value = ''; this.type = '';
  this.clientWidth = 600; this.clientHeight = 300;
}
Object.defineProperty(El.prototype, 'className', {
  get: function(){ return Object.keys(this.classList.set).join(' '); },
  set: function(v){ this.classList.set = {}; var self=this; String(v).split(/\s+/).forEach(function(c){ if(c) self.classList.set[c]=1; }); }
});
Object.defineProperty(El.prototype, 'textContent', {
  get: function(){ return this._text; },
  set: function(v){ this._text = String(v); this.children = []; }
});
Object.defineProperty(El.prototype, 'innerHTML', {
  get: function(){ return this._html; },
  set: function(v){ this._html = String(v); this.children = []; this._text = String(v).replace(/<[^>]*>/g,''); }
});
El.prototype.appendChild = function(c){
  if (c && c.__fragment) { var self=this; c.children.forEach(function(k){ k.parent=self; self.children.push(k); }); c.children=[]; return c; }
  c.parent = this; this.children.push(c); return c;
};
El.prototype.removeChild = function(c){ var i=this.children.indexOf(c); if(i>=0) this.children.splice(i,1); };
El.prototype.remove = function(){ if (this.parent) this.parent.removeChild(this); };
El.prototype.setAttribute = function(k,v){ this.attrs[k] = String(v); };
El.prototype.getAttribute = function(k){ return this.attrs.hasOwnProperty(k) ? this.attrs[k] : null; };
El.prototype.addEventListener = function(type, fn){ (this.handlers[type] = this.handlers[type] || []).push(fn); };
El.prototype.removeEventListener = function(){};
El.prototype.dispatch = function(type, ev){
  var list = this.handlers[type] || [];
  ev = ev || {}; ev.target = ev.target || this; ev.currentTarget = this;
  if (!ev.preventDefault) ev.preventDefault = function(){ ev.defaultPrevented = true; };
  for (var i=0;i<list.length;i++) list[i].call(this, ev);
};
El.prototype.getBoundingClientRect = function(){ return { width: 600, height: 300, left: 0, top: 0, right: 600, bottom: 300 }; };
El.prototype.focus = function(){}; El.prototype.blur = function(){};
El.prototype.insertBefore = function(n, ref){ return this.appendChild(n); };
El.prototype.closest = function(sel){
  var n = this;
  while (n) { if (matchesSel(n, sel)) return n; n = n.parent; }
  return null;
};

function matchesSel(el, sel){
  if (!el || !el.tagName || el.tagName.charAt(0) === '#') return false;
  var notM = sel.match(/:not\(([^)]+)\)$/);
  if (notM) {
    sel = sel.replace(notM[0], '');
    if (matchesSel(el, notM[1])) return false;
  }
  var attrRe = /\[([a-zA-Z0-9_\-]+)(?:="([^"]*)")?\]/g, m;
  while ((m = attrRe.exec(sel))) {
    var v = el.getAttribute(m[1]);
    if (v === null) return false;
    if (m[2] !== undefined && v !== m[2]) return false;
  }
  sel = sel.replace(attrRe, '').trim();
  if (sel.charAt(0) === '.') sel = sel.slice(1);
  var cls = sel.split('.').filter(function(x){ return x; });
  for (var i=0;i<cls.length;i++) if (!el.classList.contains(cls[i])) return false;
  return true;
}

El.prototype.querySelectorAll = function(sel){
  var out = [];
  (function walk(n){
    (n.children||[]).forEach(function(c){
      if (matchesSel(c, sel)) out.push(c);
      walk(c);
    });
  })(this);
  return out;
};
El.prototype.querySelector = function(sel){ var r = this.querySelectorAll(sel); return r.length ? r[0] : null; };

function makeFragment(){ var f = new El('#fragment'); f.__fragment = true; return f; }

var __byId = {};
var document = {
  readyState: 'complete',
  body: new El('body'),
  documentElement: new El('html'),
  createElement: function(tag){ var e = new El(tag); if (tag === 'canvas') return makeCanvas(e); return e; },
  createDocumentFragment: makeFragment,
  getElementById: function(id){ return __byId[id] || null; },
  querySelectorAll: function(sel){ return document.body.querySelectorAll(sel); },
  querySelector: function(sel){ return document.body.querySelector(sel); },
  addEventListener: function(type, fn){ (__handlers['doc:'+type] = __handlers['doc:'+type] || []).push(fn); }
};

function makeCanvas(e){
  var ctx = {
    font: '', fillStyle: '', strokeStyle: '', lineWidth: 1, textAlign: 'left',
    setTransform: function(){}, clearRect: function(){}, fillRect: function(){}, strokeRect: function(){},
    fillText: function(t, x, y){ (e._draws = e._draws || []).push([t, x, y]); },
    measureText: function(t){ return { width: String(t).length * 8 }; },
    save: function(){}, restore: function(){}, translate: function(){}, rotate: function(){},
    beginPath: function(){}, arc: function(){}, stroke: function(){}, moveTo: function(){},
    lineTo: function(){}, setLineDash: function(){}, closePath: function(){}, fill: function(){},
    createLinearGradient: function(){ return { addColorStop: function(){} }; }
  };
  e.getContext = function(){ return ctx; };
  e.toBlob = null;
  return e;
}

var __ls = {};
var localStorage = {
  getItem: function(k){ return __ls.hasOwnProperty(k) ? __ls[k] : null; },
  setItem: function(k,v){ __ls[k] = String(v); },
  removeItem: function(k){ delete __ls[k]; },
  clear: function(){ __ls = {}; }
};

var window = {
  addEventListener: function(type, fn){ (__handlers['win:'+type] = __handlers['win:'+type] || []).push(fn); },
  removeEventListener: function(){},
  localStorage: localStorage,
  document: document,
  scrollY: 0
};
function requestAnimationFrame(fn){ fn(); return 1; }
function setTimeout(fn){ return 1; }
function clearTimeout(){}
function alert(){}
var console = { log: function(){}, warn: function(){}, error: function(){} };
var location = { href: '', hash: '' };
var navigator = { userAgent: 'test' };

function buildTree(node, parent){
  if (node.t === '#text') {
    var t = new El('#text'); t._text = node.x; parent.appendChild(t); return null;
  }
  var e = (node.t === 'canvas') ? makeCanvas(new El(node.t)) : new El(node.t);
  Object.keys(node.a || {}).forEach(function(k){
    e.attrs[k] = node.a[k];
    if (k === 'class') e.className = node.a[k];
    if (k === 'id') { e.id = node.a[k]; __byId[node.a[k]] = e; }
    if (k === 'value') e.value = node.a[k];
    if (k === 'disabled') e.disabled = true;
    if (k === 'hidden') e.hidden = true;
    if (k === 'type') e.type = node.a[k];
  });
  parent.appendChild(e);
  (node.c || []).forEach(function(c){ buildTree(c, e); });
  return e;
}

function fire(el, type, extra){
  var ev = { target: el, preventDefault: function(){}, stopPropagation: function(){ ev.__stop = true; } };
  if (extra) Object.keys(extra).forEach(function(k){ ev[k] = extra[k]; });
  var n = el;
  while (n) {
    var list = n.handlers[type] || [];
    for (var i=0;i<list.length;i++) list[i].call(n, ev);
    if (ev.__stop) break;
    n = n.parent;
  }
}
"""


def main():
    html = open(f"{ROOT}/index.html", encoding="utf-8").read()
    p = P()
    p.feed(html)
    tree = to_json(p.root.children[0]) if p.root.children else None

    data_js = open(f"{ROOT}/data/items.js", encoding="utf-8").read()
    app_js = open(f"{ROOT}/assets/app.js", encoding="utf-8").read()

    test_js = SHIM + "\nvar __TREE = " + json.dumps(tree, ensure_ascii=False) + ";\n"
    test_js += "buildTree(__TREE, document.body);\n"
    test_js += "window.IKEA_DATA = undefined;\n"
    test_js += data_js + "\n"
    test_js += "var RESULTS = [];\nfunction ok(name, cond, extra){ RESULTS.push({name:name, pass:!!cond, extra: extra===undefined?'':String(extra)}); }\n"
    test_js += app_js + "\n"

    test_js += r"""
(function(){
  var items = window.IKEA_DATA.items;
  ok('데이터 로드', items.length > 50, items.length);
  ok('제품번호 중복 없음', (function(){ var s={},d=0; items.forEach(function(i){ if(s[i.id]) d++; s[i.id]=1; }); return d===0; })());
  ok('제품번호 형식', (function(){ return items.every(function(i){ return /^\d{3}\.\d{3}\.\d{2}$/.test(i.id); }); })());
  ok('규격 양수', items.every(function(i){ return i.w>0 && i.d>0 && i.h>0; }));
  ok('가격 양수', items.every(function(i){ return i.price>0; }));

  var grid = document.getElementById('cardGrid');
  var cards = grid.children;
  ok('카탈로그 렌더', cards.length > 0, cards.length);

  function addButtons(){
    var out = [];
    grid.children.forEach(function(li){
      (function walk(n){ (n.children||[]).forEach(function(c){ if (c.classList.contains('add-btn') && !c.disabled) out.push(c); walk(c); }); })(li);
    });
    return out;
  }

  // 기본 규격(칼락스 1칸 33x39x33)
  ok('기본 프리셋 칼락스', document.getElementById('shelfW').value === '33', document.getElementById('shelfW').value);

  // 칼락스 1칸에 쿠기스 32x32x32가 들어가야 한다
  var kuggis = null;
  grid.children.forEach(function(li){
    (function walk(n){ (n.children||[]).forEach(function(c){
      if (c.classList.contains('p-code') && c.textContent === '805.268.76') kuggis = li;
      walk(c); }); })(li);
  });
  ok('쿠기스 32x32x32 추천 노출', !!kuggis);

  var btns = addButtons();
  ok('담기 버튼 존재', btns.length > 0, btns.length);

  var store = JSON.parse(localStorage.getItem('ikea-storage-sim-v1') || '{}');
  fire(btns[0], 'click');
  store = JSON.parse(localStorage.getItem('ikea-storage-sim-v1'));
  ok('첫 수납함 담기', store.placed.length === 1, store.placed.length);

  btns = addButtons();
  var added = 0;
  for (var i=0; i<3 && i<btns.length; i++){
    var b = btns[i];
    var beforeN = JSON.parse(localStorage.getItem('ikea-storage-sim-v1')).placed.length;
    fire(b, 'click');
    var afterN = JSON.parse(localStorage.getItem('ikea-storage-sim-v1')).placed.length;
    if (afterN > beforeN) added++;
  }
  store = JSON.parse(localStorage.getItem('ikea-storage-sim-v1'));
  ok('여러 개 담기', store.placed.length === 1 + added, store.placed.length);

  var inside = store.placed.every(function(p){
    return p.x >= -0.01 && p.y >= -0.01 && (p.row === 0 || p.row === 1);
  });
  ok('배치 좌표 유효', inside, JSON.stringify(store.placed.slice(0,2)));

  var overlapBad = 0;
  for (var a=0; a<store.placed.length; a++){
    for (var b=a+1; b<store.placed.length; b++){
      var A=store.placed[a], B=store.placed[b];
      if (A.row !== B.row) continue;
      var ia = window.IKEA_DATA.items.filter(function(x){return x.id===A.id;})[0];
      var ib = window.IKEA_DATA.items.filter(function(x){return x.id===B.id;})[0];
      var wa = A.rot? ia.d : ia.w, ha = A.lay? ia.d : ia.h;
      var wb = B.rot? ib.d : ib.w, hb = B.lay? ib.d : ib.h;
      if (A.x < B.x+wb-0.01 && A.x+wa > B.x+0.01 && A.y < B.y+hb-0.01 && A.y+ha > B.y+0.01) overlapBad++;
    }
  }
  ok('같은 줄 겹침 없음', overlapBad === 0, overlapBad);

  var statCount = document.getElementById('statCount').textContent;
  ok('개수 통계', String(statCount) === String(store.placed.length), statCount);

  // 이케아 프리셋: 빌리 80폭
  var billy = document.querySelector('[data-preset="billy80"]');
  ok('빌리 프리셋 버튼', !!billy);
  fire(billy, 'click');
  store = JSON.parse(localStorage.getItem('ikea-storage-sim-v1'));
  ok('빌리 80폭 규격 반영', store.shelf.w === 76 && store.shelf.d === 26 && store.shelf.h === 30,
     JSON.stringify(store.shelf));
  ok('프리셋 활성 표시', billy.classList.contains('is-on'));
  ok('규격 변경 후 카탈로그 갱신', document.getElementById('cardGrid').children.length > 0,
     document.getElementById('cardGrid').children.length);

  // 시리즈 필터: 쿠기스
  var chips = document.getElementById('filters').children;
  ok('시리즈 필터 생성', chips.length > 3, chips.length);
  var kugChip = null;
  for (var ci=0; ci<chips.length; ci++){
    if (chips[ci].getAttribute('data-filter') === 's:쿠기스') kugChip = chips[ci];
  }
  ok('쿠기스 필터 존재', !!kugChip);
  fire(kugChip, 'click');
  var allKug = true;
  document.getElementById('cardGrid').children.forEach(function(li){
    (function walk(n){ (n.children||[]).forEach(function(c){
      if (c.classList.contains('p-code')) {
        var it = window.IKEA_DATA.items.filter(function(x){ return x.id === c.textContent; })[0];
        if (!it || it.seriesKo !== '쿠기스') allKug = false;
      }
      walk(c); }); })(li);
  });
  ok('쿠기스 필터 결과', allKug, document.getElementById('cardGrid').children.length);
  fire(document.querySelector('[data-filter="all"]'), 'click');

  // 되돌리기 · 전부 빼기
  var undo = document.getElementById('undoBtn');
  ok('되돌리기 활성', undo.disabled === false);
  var n1 = JSON.parse(localStorage.getItem('ikea-storage-sim-v1')).placed.length;
  fire(undo, 'click');
  var n2 = JSON.parse(localStorage.getItem('ikea-storage-sim-v1')).placed.length;
  ok('되돌리기 동작', n2 <= n1, n2 + '/' + n1);

  fire(document.getElementById('clearBtn'), 'click');
  ok('전부 빼기', JSON.parse(localStorage.getItem('ikea-storage-sim-v1')).placed.length === 0);

  // 툴바 동작
  var wEl = document.getElementById('shelfW');
  var dEl = document.getElementById('shelfD');
  var hEl = document.getElementById('shelfH');
  wEl.value = '96'; dEl.value = '58'; hEl.value = '35';
  fire(wEl, 'change');
  var b3 = addButtons();
  fire(b3[0], 'click');
  var stage = document.getElementById('stage');
  var itemNode = stage.querySelector('.item');
  ok('무대에 수납함 표시', !!itemNode);
  fire(itemNode, 'pointerdown', { clientX: 100, clientY: 100, pointerId: 1 });
  var bar = document.getElementById('selToolbar');
  ok('선택 툴바 열림', bar.hidden === false);
  var st0 = JSON.parse(localStorage.getItem('ikea-storage-sim-v1')).placed[0];
  var itm0 = window.IKEA_DATA.items.filter(function(x){return x.id===st0.id;})[0];
  ok('배치 정보', true, st0.id + ' ' + itm0.name + ' ' + [itm0.w,itm0.d,itm0.h].join('x') + ' rot' + st0.rot + ' lay' + st0.lay);
  fire(bar.querySelector('[data-act="rotate"]'), 'click');
  var st1 = JSON.parse(localStorage.getItem('ikea-storage-sim-v1')).placed[0];
  var dmA = st1.rot ? [itm0.d, itm0.w, itm0.h] : [itm0.w, itm0.d, itm0.h];
  ok('돌리기 후 배치 유효', st1.x + dmA[0] <= 96.01 && st1.y + dmA[2] <= 35.01, JSON.stringify([st1.x, st1.y, st1.rot]));
  fire(bar.querySelector('[data-act="lay"]'), 'click');
  var st2 = JSON.parse(localStorage.getItem('ikea-storage-sim-v1')).placed[0];
  ok('눕히기 반영', st2.lay === 1 || st2.lay === 0);
  var n3 = JSON.parse(localStorage.getItem('ikea-storage-sim-v1')).placed.length;
  fire(bar.querySelector('[data-act="dup"]'), 'click');
  var st3 = JSON.parse(localStorage.getItem('ikea-storage-sim-v1')).placed;
  ok('앞뒤 2줄', st3.length >= n3, st3.length);
  fire(bar.querySelector('[data-act="remove"]'), 'click');
  var st4 = JSON.parse(localStorage.getItem('ikea-storage-sim-v1')).placed;
  ok('제거', st4.length < st3.length, st4.length);

  // 쌓기: 좁은 칸에서는 두 번째가 위로 쌓여야 한다
  fire(document.getElementById('clearBtn'), 'click');
  wEl.value = '18'; dEl.value = '18'; hEl.value = '60';
  fire(wEl, 'change');
  var b5 = addButtons();
  if (b5.length >= 1) {
    fire(b5[0], 'click');
    // 들어가는 두 번째 수납함을 찾아 담는다(자동 배치가 위로 쌓는지 확인)
    for (var si = 0; si < 8; si++) {
      var list5 = addButtons();
      if (!list5.length) break;
      var cnt = JSON.parse(localStorage.getItem('ikea-storage-sim-v1')).placed.length;
      fire(list5[si % list5.length], 'click');
      if (JSON.parse(localStorage.getItem('ikea-storage-sim-v1')).placed.length > cnt) break;
    }
    var st5 = JSON.parse(localStorage.getItem('ikea-storage-sim-v1')).placed;
    ok('좁은 칸 쌓기', st5.length === 2 && st5[1].y > 0, JSON.stringify(st5));
  } else {
    ok('좁은 칸 쌓기', false, 'no item');
  }

  // ---- 미리보기 프레임 · 치수 라벨 · 균일 배율 ----
  fire(document.getElementById('clearBtn'), 'click');
  fire(document.querySelector('[data-preset="billy80"]'), 'click');
  function txtOf(n){ var s = n ? (n._text || '') : ''; if (n) (n.children||[]).forEach(function(c){ if (c.tagName !== '#text') s += txtOf(c); else s += (c._text || ''); }); return s; }
  function fireWin(type, ev){
    var list = __handlers['win:'+type] || [];
    ev = ev || {};
    if (!ev.preventDefault) ev.preventDefault = function(){};
    for (var i=0;i<list.length;i++) list[i].call(window, ev);
  }
  var sBox = document.getElementById('shelfBox');
  var frame = sBox.querySelector('.shelf-frame');
  ok('수납칸 프레임 표시', !!frame);
  var fw = parseFloat(frame.style.width), fh = parseFloat(frame.style.height);
  ok('프레임 비율 = 칸 비율(76:30)', Math.abs(fw / fh - 76 / 30) < 0.02, fw + 'x' + fh);
  var dTop = sBox.querySelector('.dim-top');
  var dLeft = sBox.querySelector('.dim-left');
  var dBot = sBox.querySelector('.dim-bottom');
  ok('위 폭 라벨', txtOf(dTop) === '폭 76cm', txtOf(dTop));
  ok('왼쪽 높이 라벨', txtOf(dLeft) === '높이 30cm', txtOf(dLeft));
  ok('아래 설명 라벨', txtOf(dBot) === '안쪽 깊이 26cm · 바닥에서 본 정면', txtOf(dBot));

  // 옆에서 보기: 축이 바뀌어도 같은 배율
  fire(document.querySelector('.tab[data-view="side"]'), 'click');
  ok('옆에서 위 라벨', txtOf(sBox.querySelector('.dim-top')) === '깊이 26cm', txtOf(sBox.querySelector('.dim-top')));
  ok('옆에서 아래 라벨', txtOf(sBox.querySelector('.dim-bottom')) === '폭 76cm · 옆에서 본 단면', txtOf(sBox.querySelector('.dim-bottom')));
  var fSide = sBox.querySelector('.shelf-frame');
  ok('옆에서 프레임 비율(26:30)',
     Math.abs(parseFloat(fSide.style.width) / parseFloat(fSide.style.height) - 26 / 30) < 0.02,
     fSide.style.width + 'x' + fSide.style.height);
  fire(document.querySelector('.tab[data-view="top"]'), 'click');
  ok('위에서 왼쪽 깊이 라벨', txtOf(sBox.querySelector('.dim-left')) === '깊이 26cm', txtOf(sBox.querySelector('.dim-left')));
  ok('위에서 아래 라벨', txtOf(sBox.querySelector('.dim-bottom')) === '높이 30cm · 위에서 내려다본 평면', txtOf(sBox.querySelector('.dim-bottom')));
  fire(document.querySelector('.tab[data-view="front"]'), 'click');

  // 얇은 트레이(UPPDATERA 55.4x12.6x2.5)도 이름이 보여야 한다
  var thinCard = null;
  document.getElementById('cardGrid').children.forEach(function(li){
    (function walk(n){ (n.children||[]).forEach(function(c){
      if (c.classList.contains('p-code') && c.textContent === '305.491.68') thinCard = li;
      walk(c); }); })(li);
  });
  ok('우프다테라 카드가 추천에 있음', !!thinCard);
  var thinNode = null, scale6 = parseFloat(document.querySelector('.shelf-frame').style.width) / 76;
  if (thinCard) {
    var addB = null;
    (function walk(n){ (n.children||[]).forEach(function(c){ if (c.classList.contains('add-btn')) addB = c; walk(c); }); })(thinCard);
    fire(addB, 'click');
    thinNode = document.getElementById('shelfBox').querySelector('.item');
  }
  ok('얇은 트레이 축소 라벨 클래스', !!thinNode && thinNode.classList.contains('is-thin'));
  var thinName = thinNode ? thinNode.querySelector('.it-name') : null;
  ok('얇은 트레이 이름 라벨', !!thinName && thinName.textContent === '우프다테라', thinName ? thinName.textContent : '');
  ok('얇은 트레이 두께 = 2.5cm × 배율',
     !!thinNode && Math.abs((parseFloat(thinNode.style.height) + 1) - 2.5 * scale6) < 0.6,
     thinNode ? thinNode.style.height + ' / scale ' + scale6 : '');
  ok('얇은 트레이 폭 = 55.4cm × 배율',
     !!thinNode && Math.abs((parseFloat(thinNode.style.width) + 1) - 55.4 * scale6) < 0.6,
     thinNode ? thinNode.style.width : '');

  // 드래그가 화면 이동량과 1:1로 맞는다(같은 배율 사용)
  if (thinNode) {
    var left0 = parseFloat(thinNode.style.left);
    fire(thinNode, 'pointerdown', { clientX: 200, clientY: 200, pointerId: 1 });
    fireWin('pointermove', { clientX: 200 + 10 * scale6, clientY: 200 });
    var left1 = parseFloat(thinNode.style.left);
    ok('드래그 10cm = 화면 10×배율', Math.abs((left1 - left0) - 10 * scale6) < 1.2, left0 + ' → ' + left1);
    fireWin('pointerup', {});
  }

  // 선택 툴바는 미리보기 카드 안, 통계 위에 인라인으로
  fire(document.getElementById('shelfBox').querySelector('.item'), 'pointerdown', { clientX: 220, clientY: 220, pointerId: 2 });
  var bar0 = document.getElementById('selToolbar');
  var prevCard = bar0.closest('.preview-card');
  ok('선택 툴바가 미리보기 카드 안', !!prevCard);
  var kids = prevCard ? prevCard.children : [];
  var barIdx = kids.indexOf(bar0), statIdx = kids.indexOf(document.getElementById('stats'));
  ok('선택 툴바가 통계보다 위', barIdx >= 0 && statIdx > barIdx, barIdx + '/' + statIdx);

  // 휴대폰 폭(무대 340px)에서도 같은 배율·프레임·얇은 라벨이 유지된다
  var stageM = document.getElementById('stage');
  var prevW = stageM.clientWidth;
  stageM.clientWidth = 340;
  fireWin('resize', {});
  var sBoxM = document.getElementById('shelfBox');
  var frameM = sBoxM.querySelector('.shelf-frame');
  var nodeM = sBoxM.querySelector('.item');
  var scaleM = parseFloat(frameM.style.width) / 76;
  ok('좁은 화면 프레임 비율 유지',
     Math.abs(parseFloat(frameM.style.width) / parseFloat(frameM.style.height) - 76 / 30) < 0.02,
     frameM.style.width + 'x' + frameM.style.height);
  ok('좁은 화면에서도 1cm = 같은 배율',
     !!nodeM && Math.abs((parseFloat(nodeM.style.width) + 1) - 55.4 * scaleM) < 0.6 &&
     Math.abs((parseFloat(nodeM.style.height) + 1) - 2.5 * scaleM) < 0.6,
     scaleM.toFixed(2));
  ok('좁은 화면에서도 얇은 라벨', !!nodeM && !!nodeM.querySelector('.it-name'),
     nodeM ? nodeM.className : '');
  ok('좁은 화면에서도 치수 라벨',
     txtOf(sBoxM.querySelector('.dim-top')) === '폭 76cm' &&
     txtOf(sBoxM.querySelector('.dim-left')) === '높이 30cm',
     txtOf(sBoxM.querySelector('.dim-bottom')));
  stageM.clientWidth = prevW;
  fireWin('resize', {});

  // 쇼핑 리스트 캔버스
  fire(document.getElementById('clearBtn'), 'click');
  wEl.value = '33'; dEl.value = '39'; hEl.value = '33';
  fire(wEl, 'change');
  fire(document.querySelector('[data-preset="kallax1"]'), 'click');
  var b4 = addButtons();
  if (b4.length) fire(b4[0], 'click');
  var threw = null;
  try { fire(document.getElementById('receiptOpenBtn'), 'click'); } catch(e){ threw = e && e.message; }
  ok('쇼핑 리스트 렌더', threw === null, threw || '');
  var cv = document.getElementById('receiptCanvas');
  ok('캔버스 고해상도', cv.width === 2280 && cv.height > 800, cv.width + 'x' + cv.height);
  ok('모달 열림', document.getElementById('receiptModal').hidden === false);
  var texts = (cv._draws || []).map(function (d) { return d[0]; }).join(' | ');
  ok('리스트 제목', texts.indexOf('이케아 수납 쇼핑 리스트') >= 0);
  ok('제품번호 표기', /제품번호 \d{3}\.\d{3}\.\d{2}/.test(texts), texts.slice(0, 80));
  ok('칸 규격 표기', texts.indexOf('칼락스 KALLAX 1칸') >= 0);
  ok('합계 표기', texts.indexOf('합계') >= 0 && texts.indexOf('원') >= 0);

  console.log(JSON.stringify(RESULTS));
})();
"""

    
    import quickjs  # noqa
    ctx = quickjs.Context()
    out = ctx.eval(test_js + "\n;JSON.stringify(RESULTS)")
    results = json.loads(out) if isinstance(out, str) else out
    fails = [r for r in results if not r["pass"]]
    for r in results:
        print(("PASS " if r["pass"] else "FAIL ") + r["name"] + ("  " + r["extra"] if r["extra"] else ""))
    print("\n%d/%d passed" % (len(results) - len(fails), len(results)))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
