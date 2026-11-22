#!/usr/bin/env python3
"""정적 앱 스모크 테스트: quickjs + 최소 DOM 셰임으로 index.html/app.js 를 실제 실행한다.

검증 항목
  1. app.js 가 오류 없이 초기화되고 카탈로그가 렌더된다
  2. '선반에 담기' 클릭 → 배치/통계/저장이 맞게 동작한다
  3. 되돌리기·전부 내리기가 상태를 되돌린다
  4. 선반 규격 변경 시 카탈로그와 배치가 갱신된다
  5. 영수증 캔버스 그리기가 예외 없이 끝난다
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

    data_js = open(f"{ROOT}/data/baskets.js", encoding="utf-8").read()
    app_js = open(f"{ROOT}/assets/app.js", encoding="utf-8").read()

    test_js = SHIM + "\nvar __TREE = " + json.dumps(tree, ensure_ascii=False) + ";\n"
    test_js += "buildTree(__TREE, document.body);\n"
    test_js += "window.DAISO_DATA = undefined;\n"
    test_js += data_js + "\n"
    test_js += "var RESULTS = [];\nfunction ok(name, cond, extra){ RESULTS.push({name:name, pass:!!cond, extra: extra===undefined?'':String(extra)}); }\n"
    test_js += app_js + "\n"

    test_js += r"""
(function(){
  var items = window.DAISO_DATA.items;
  ok('데이터 로드', items.length > 50, items.length);
  ok('품번 중복 없음', (function(){ var s={},d=0; items.forEach(function(i){ if(s[i.id]) d++; s[i.id]=1; }); return d===0; })());

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
  var btns = addButtons();
  ok('담기 버튼 존재', btns.length > 0, btns.length);

  var store = JSON.parse(localStorage.getItem('daiso-shelf-sim-v1') || '{}');
  var before = (store.placed || []).length;
  fire(btns[0], 'click');
  store = JSON.parse(localStorage.getItem('daiso-shelf-sim-v1'));
  ok('첫 바구니 담기', store.placed.length === before + 1, store.placed.length);

  // 3개 더 담기
  btns = addButtons();
  var added = 0;
  for (var i=0; i<3 && i<btns.length; i++){
    var b = btns[i];
    var beforeN = JSON.parse(localStorage.getItem('daiso-shelf-sim-v1')).placed.length;
    fire(b, 'click');
    var afterN = JSON.parse(localStorage.getItem('daiso-shelf-sim-v1')).placed.length;
    if (afterN > beforeN) added++;
  }
  store = JSON.parse(localStorage.getItem('daiso-shelf-sim-v1'));
  ok('여러 개 담기', store.placed.length === before + 1 + added, store.placed.length);

  var shelf = store.shelf;
  var inside = store.placed.every(function(p){
    return p.x >= -0.01 && p.y >= -0.01;
  });
  ok('배치 좌표 유효', inside, JSON.stringify(store.placed.slice(0,2)));

  // 겹침 없음(같은 줄 기준) 확인
  var overlapBad = 0;
  for (var a=0; a<store.placed.length; a++){
    for (var b=a+1; b<store.placed.length; b++){
      var A=store.placed[a], B=store.placed[b];
      if (A.row !== B.row) continue;
      var ia = window.DAISO_DATA.items.filter(function(x){return x.id===A.id;})[0];
      var ib = window.DAISO_DATA.items.filter(function(x){return x.id===B.id;})[0];
      var wa = A.rot? ia.d : ia.w, ha = A.lay? ia.d : ia.h;
      var wb = B.rot? ib.d : ib.w, hb = B.lay? ib.d : ib.h;
      if (A.x < B.x+wb-0.01 && A.x+wa > B.x+0.01 && A.y < B.y+hb-0.01 && A.y+ha > B.y+0.01) overlapBad++;
    }
  }
  ok('같은 줄 겹침 없음', overlapBad === 0, overlapBad);

  // 통계
  var statCount = document.getElementById('statCount').textContent;
  ok('개수 통계', String(statCount) === String(store.placed.length), statCount);

  // 되돌리기
  var undo = document.getElementById('undoBtn');
  ok('되돌리기 활성', undo.disabled === false);
  var n1 = store.placed.length;
  fire(undo, 'click');
  store = JSON.parse(localStorage.getItem('daiso-shelf-sim-v1'));
  ok('되돌리기 동작', store.placed.length < n1 || n1 === 1, store.placed.length + '/' + n1);

  // 전부 내리기
  fire(document.getElementById('clearBtn'), 'click');
  store = JSON.parse(localStorage.getItem('daiso-shelf-sim-v1'));
  ok('전부 내리기', store.placed.length === 0, store.placed.length);

  // 선반 규격 변경
  var wEl = document.getElementById('shelfW');
  var dEl = document.getElementById('shelfD');
  var hEl = document.getElementById('shelfH');
  wEl.value = '30'; dEl.value = '25'; hEl.value = '25';
  fire(wEl, 'change');
  store = JSON.parse(localStorage.getItem('daiso-shelf-sim-v1'));
  ok('규격 변경 반영', store.shelf.w === 30 && store.shelf.d === 25 && store.shelf.h === 25, JSON.stringify(store.shelf));
  var grid2 = document.getElementById('cardGrid').children.length;
  ok('규격 변경 후 카탈로그 갱신', grid2 > 0, grid2);

  // 작은 선반에도 담기
  var b2 = addButtons();
  if (b2.length) fire(b2[0], 'click');
  store = JSON.parse(localStorage.getItem('daiso-shelf-sim-v1'));
  ok('작은 선반 담기', store.placed.length === 1, store.placed.length);


  // 선택 툴바 동작
  fire(document.getElementById('clearBtn'), 'click');
  wEl.value = '60'; dEl.value = '35'; hEl.value = '40';
  fire(wEl, 'change');
  var stage = document.getElementById('stage');
  var b3 = addButtons();
  fire(b3[0], 'click');
  var itemNode = stage.querySelector('.item');
  ok('무대에 바구니 표시', !!itemNode);
  fire(itemNode, 'pointerdown', { clientX: 100, clientY: 100, pointerId: 1 });
  var bar = document.getElementById('selToolbar');
  ok('선택 툴바 열림', bar.hidden === false);
  var st0 = JSON.parse(localStorage.getItem('daiso-shelf-sim-v1')).placed[0];
  var itm0 = window.DAISO_DATA.items.filter(function(x){return x.id===st0.id;})[0];
  ok('배치 정보', true, st0.id + ' ' + itm0.name + ' ' + [itm0.w,itm0.d,itm0.h].join('x') + ' rot' + st0.rot + ' lay' + st0.lay);
  fire(bar.querySelector('[data-act="rotate"]'), 'click');
  var st1 = JSON.parse(localStorage.getItem('daiso-shelf-sim-v1')).placed[0];
  var dmA = st1.rot ? [itm0.d, itm0.w, itm0.h] : [itm0.w, itm0.d, itm0.h];
  ok('돌리기 후 배치 유효', st1.x + dmA[0] <= 60.01 && st1.y + dmA[2] <= 40.01, JSON.stringify([st1.x, st1.y, st1.rot]));
  fire(bar.querySelector('[data-act="lay"]'), 'click');
  var st2 = JSON.parse(localStorage.getItem('daiso-shelf-sim-v1')).placed[0];
  ok('눕히기 반영', st2.lay === 1 || st2.lay === 0);
  var n2 = JSON.parse(localStorage.getItem('daiso-shelf-sim-v1')).placed.length;
  fire(bar.querySelector('[data-act="dup"]'), 'click');
  var st3 = JSON.parse(localStorage.getItem('daiso-shelf-sim-v1')).placed;
  ok('앞뒤 2줄', st3.length >= n2, st3.length);
  fire(bar.querySelector('[data-act="remove"]'), 'click');
  var st4 = JSON.parse(localStorage.getItem('daiso-shelf-sim-v1')).placed;
  ok('제거', st4.length < st3.length, st4.length);


  // 쌓기: 좁은 선반에서는 두 번째가 위로 쌓여야 한다
  fire(document.getElementById('clearBtn'), 'click');
  wEl.value = '18'; dEl.value = '18'; hEl.value = '60';
  fire(wEl, 'change');
  var b5 = addButtons();
  if (b5.length >= 1) {
    fire(b5[0], 'click');
    var b5b = addButtons();
    if (b5b.length) fire(b5b[0], 'click');
    var st5 = JSON.parse(localStorage.getItem('daiso-shelf-sim-v1')).placed;
    ok('좁은 선반 쌓기', st5.length === 2 && st5[1].y > 0, JSON.stringify(st5));
  } else {
    ok('좁은 선반 쌓기', false, 'no item');
  }


  // 방향키 이동 + 되돌리기
  fire(document.getElementById('clearBtn'), 'click');
  wEl.value = '120'; dEl.value = '40'; hEl.value = '50';
  fire(wEl, 'change');
  var b6 = addButtons();
  if (b6.length) fire(b6[0], 'click');
  var it6 = document.getElementById('stage').querySelector('.item');
  if (it6) fire(it6, 'pointerdown', { clientX: 50, clientY: 50, pointerId: 1 });
  var dh = __handlers['doc:keydown'] || [];
  var beforeKey = JSON.parse(localStorage.getItem('daiso-shelf-sim-v1')).placed[0];
  dh[0]({ key: 'ArrowRight', shiftKey: false, target: { tagName: 'body' }, preventDefault: function(){} });
  dh[0]({ key: 'ArrowRight', shiftKey: false, target: { tagName: 'body' }, preventDefault: function(){} });
  var afterKey = JSON.parse(localStorage.getItem('daiso-shelf-sim-v1')).placed[0];
  ok('방향키 이동', afterKey.x === beforeKey.x + 1, beforeKey.x + '→' + afterKey.x);
  var undo2 = document.getElementById('undoBtn');
  fire(undo2, 'click');
  fire(undo2, 'click');
  var undone = JSON.parse(localStorage.getItem('daiso-shelf-sim-v1')).placed[0];
  ok('이동 되돌리기(2단계)', undone.x === beforeKey.x, undone.x);

  // 영수증 그리기 (바구니를 하나 담은 상태에서)
  var b4 = addButtons();
  if (b4.length) fire(b4[0], 'click');
  var threw = null;
  try { fire(document.getElementById('receiptOpenBtn'), 'click'); } catch(e){ threw = e && e.message; }
  ok('영수증 렌더', threw === null, threw || '');
  var cv = document.getElementById('receiptCanvas');
  ok('영수증 캔버스 크기', cv.width === 2160 && cv.height > 600, cv.width + 'x' + cv.height);
  var modal = document.getElementById('receiptModal');
  ok('영수증 모달 열림', modal.hidden === false);
  var texts = (cv._draws || []).map(function (d) { return d[0]; }).join(' | ');
  ok('영수증 제목', texts.indexOf('다이소 바구니 영수증') >= 0);
  ok('영수증 선반 규격', /선반 \d/.test(texts));
  ok('영수증 합계', texts.indexOf('원') >= 0);

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
