/* تلميح ملخص المباراة: يظهر عند المرور بالماوس على مباراة منتهية تحمل
   data-summary (أو بالتركيز بلوحة المفاتيح، أو باللمس على الجوال).
   يُلحق الصندوق بـ <body> بموضع ثابت (fixed) حتى لا يُقتطع بفعل overflow
   عمود النتائج. كل البيانات من مصدر خارجي، لذا لا نستخدم innerHTML للنصوص —
   نعتمد textContent فقط. */
(function () {
  'use strict';

  var GAP = 12;
  var HIDE_DELAY = 140;

  var tip = null;
  var active = null;
  var hideTimer = null;

  // أيقونات ثابتة (ليست بيانات خارجية) — آمنة في innerHTML
  var ICONS = {
    goal: '<svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true"><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="2"/><path d="m12 7 4.2 3.05-1.6 4.95H9.4L7.8 10.05Z" fill="currentColor"/></svg>',
    own: '<svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true"><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="2"/><path d="m12 7 4.2 3.05-1.6 4.95H9.4L7.8 10.05Z" fill="#e06666"/></svg>',
    yellow: '<svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true"><rect x="7.5" y="3" width="9" height="18" rx="2" fill="#f4c430"/></svg>',
    red: '<svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true"><rect x="7.5" y="3" width="9" height="18" rx="2" fill="#e23b3b"/></svg>',
    sub: '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17 3l3 3-3 3"/><path d="M20 6H9.5A3.5 3.5 0 0 0 6 9.5"/><path d="M7 21l-3-3 3-3"/><path d="M4 18h10.5a3.5 3.5 0 0 0 3.5-3.5"/></svg>',
    assist: '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="7" cy="7" r="3"/><path d="M14 17l4-4-4-4"/><path d="M18 13H9"/></svg>'
  };

  function icon(name) {
    var span = document.createElement('span');
    span.className = 'tip-ico tip-ico-' + name;
    span.innerHTML = ICONS[name] || '';
    return span;
  }

  function text(cls, value) {
    var span = document.createElement('span');
    if (cls) span.className = cls;
    span.textContent = value == null ? '' : String(value);
    return span;
  }

  function section(title) {
    var box = document.createElement('div');
    box.className = 'tip-sec';
    var heading = document.createElement('p');
    heading.className = 'tip-sec-title';
    heading.textContent = title;
    box.appendChild(heading);
    return box;
  }

  function line(iconName) {
    var row = document.createElement('div');
    row.className = 'tip-line';
    if (iconName) row.appendChild(icon(iconName));
    return row;
  }

  function playerAndTeam(player, team) {
    var frag = document.createDocumentFragment();
    frag.appendChild(text('tip-name', player));
    if (team) frag.appendChild(text('tip-team', ' · ' + team));
    return frag;
  }

  function render(row, data) {
    tip.textContent = '';

    var names = row.querySelectorAll('.side-name');
    var score = row.querySelector('.score');
    var head = document.createElement('div');
    head.className = 'tip-head';
    head.appendChild(text('tip-head-team', names[0] ? names[0].textContent.trim() : ''));
    head.appendChild(text('tip-head-score', score ? score.textContent.trim() : ''));
    head.appendChild(text('tip-head-team', names[1] ? names[1].textContent.trim() : ''));
    tip.appendChild(head);

    if (data.goals && data.goals.length) {
      var goals = section('الأهداف');
      data.goals.forEach(function (g) {
        var l = line(g.kind === 'own' ? 'own' : 'goal');
        l.appendChild(text('tip-min', g.minute));
        l.appendChild(playerAndTeam(g.player, g.team));
        if (g.kind === 'penalty') l.appendChild(text('tip-tag', 'ركلة جزاء'));
        if (g.kind === 'own') l.appendChild(text('tip-tag tip-tag-own', 'هدف عكسي'));
        goals.appendChild(l);
      });
      tip.appendChild(goals);
    }

    if (data.cards && data.cards.length) {
      var cards = section('البطاقات');
      data.cards.forEach(function (c) {
        var l = line(c.kind === 'red' ? 'red' : 'yellow');
        l.appendChild(text('tip-min', c.minute));
        l.appendChild(playerAndTeam(c.player, c.team));
        cards.appendChild(l);
      });
      tip.appendChild(cards);
    }

    if (data.subs && data.subs.length) {
      var subs = section('التبديلات');
      data.subs.forEach(function (s) {
        var l = line('sub');
        l.appendChild(text('tip-min', s.minute));
        var box = document.createElement('span');
        box.className = 'tip-sub';
        var inEl = document.createElement('span');
        inEl.className = 'tip-sub-in';
        inEl.textContent = 'دخل: ' + (s.in || '—');
        var outEl = document.createElement('span');
        outEl.className = 'tip-sub-out';
        outEl.textContent = 'خرج: ' + (s.out || '—');
        box.appendChild(inEl);
        box.appendChild(outEl);
        l.appendChild(box);
        subs.appendChild(l);
      });
      tip.appendChild(subs);
    }

    if (data.assists && data.assists.length) {
      var assists = section('صنّاع الأهداف');
      data.assists.forEach(function (a) {
        var l = line('assist');
        l.appendChild(playerAndTeam(a.player, a.team));
        if (a.count > 1) l.appendChild(text('tip-tag', '×' + a.count));
        assists.appendChild(l);
      });
      tip.appendChild(assists);
    }
  }

  function place(row) {
    var rect = row.getBoundingClientRect();
    var w = tip.offsetWidth;
    var h = tip.offsetHeight;
    var vw = window.innerWidth;
    var vh = window.innerHeight;

    var x = rect.right + GAP;
    if (x + w > vw - 8) x = rect.left - w - GAP;
    if (x < 8) x = 8;
    if (x + w > vw - 8) x = Math.max(8, vw - w - 8);

    var y = rect.top;
    if (y + h > vh - 8) y = vh - 8 - h;
    if (y < 8) y = 8;

    tip.style.left = Math.round(x) + 'px';
    tip.style.top = Math.round(y) + 'px';
  }

  function ensureTip() {
    if (tip) return tip;
    tip = document.createElement('div');
    tip.className = 'match-tip';
    tip.setAttribute('role', 'tooltip');
    tip.hidden = true;
    document.body.appendChild(tip);
    return tip;
  }

  function show(row) {
    var raw = row.getAttribute('data-summary');
    if (!raw) return;
    var data;
    try { data = JSON.parse(raw); } catch (e) { return; }
    ensureTip();
    render(row, data);
    tip.hidden = false;
    active = row;
    place(row);
  }

  function hide() {
    clearTimeout(hideTimer);
    if (!tip) return;
    tip.hidden = true;
    active = null;
  }

  function scheduleHide() {
    clearTimeout(hideTimer);
    hideTimer = setTimeout(hide, HIDE_DELAY);
  }

  function closestRow(target) {
    return target && target.closest ? target.closest('.match[data-summary]') : null;
  }

  document.addEventListener('mouseover', function (e) {
    var row = closestRow(e.target);
    if (row) {
      clearTimeout(hideTimer);
      if (row !== active) show(row);
      return;
    }
    if (tip && !tip.hidden && tip.contains(e.target)) {
      clearTimeout(hideTimer);
      return;
    }
    if (active) scheduleHide();
  });

  document.addEventListener('mouseout', function (e) {
    // مغادرة النافذة كلياً بلا هدف وجهة
    if (!e.relatedTarget && active) scheduleHide();
  });

  document.addEventListener('focusin', function (e) {
    var row = closestRow(e.target);
    if (row) { clearTimeout(hideTimer); show(row); }
  });

  document.addEventListener('focusout', function (e) {
    var row = closestRow(e.target);
    if (row && row === active) scheduleHide();
  });

  document.addEventListener('click', function (e) {
    var row = closestRow(e.target);
    if (row) {
      if (row === active) hide(); else show(row);
    } else if (active && tip && !tip.contains(e.target)) {
      hide();
    }
  });

  window.addEventListener('scroll', function () { if (active) place(active); }, true);
  window.addEventListener('resize', function () { if (active) place(active); });
})();
