/* سلايدر الأخبار الرئيسي: انتقال متقاطع احترافي مع تقريب سينمائي للصورة،
   أسهم ونقاط تنقل، تقدم تلقائي، توقف عند المؤشر، وسحب باللمس. */
(function () {
  'use strict';

  function goTo(root, index) {
    var slides = root.querySelectorAll('.slider-slide');
    var dots = root.querySelectorAll('.slider-dot');
    var count = slides.length;
    if (!count) return;
    var cur = index % count;
    if (cur < 0) cur += count;
    slides.forEach(function (s, i) { s.classList.toggle('is-active', i === cur); });
    dots.forEach(function (d, i) { d.classList.toggle('is-active', i === cur); });
    root._cur = cur;
  }

  function init(root) {
    var slides = root.querySelectorAll('.slider-slide');
    if (slides.length < 2) return; /* شريحة وحيدة: تعرض ثابتة بلا تنقل */
    var dotsBox = root.querySelector('.slider-dots');
    var prevBtn = root.querySelector('.slider-prev');
    var nextBtn = root.querySelector('.slider-next');
    var timer = null;
    var INTERVAL = 5500;

    slides.forEach(function (_, i) {
      var d = document.createElement('button');
      d.type = 'button';
      d.className = 'slider-dot' + (i === 0 ? ' is-active' : '');
      d.setAttribute('aria-label', 'الخبر رقم ' + (i + 1));
      d.addEventListener('click', function () { goTo(root, i); restart(); });
      dotsBox.appendChild(d);
    });
    root._cur = 0;

    function next() { goTo(root, root._cur + 1); }
    function prev() { goTo(root, root._cur - 1); }
    function restart() { stop(); timer = setInterval(next, INTERVAL); }
    function stop() { if (timer) { clearInterval(timer); timer = null; } }

    prevBtn.addEventListener('click', function () { prev(); restart(); });
    nextBtn.addEventListener('click', function () { next(); restart(); });

    root.addEventListener('mouseenter', stop);
    root.addEventListener('mouseleave', restart);

    /* سحب باللمس: باتجاه اليسار = الخبر التالي (اتجاه القراءة RTL) */
    var touchX = null;
    root.addEventListener('touchstart', function (e) {
      touchX = e.touches[0].clientX; stop();
    }, { passive: true });
    root.addEventListener('touchend', function (e) {
      if (touchX === null) return;
      var dx = e.changedTouches[0].clientX - touchX;
      if (Math.abs(dx) > 40) { if (dx < 0) next(); else prev(); restart(); }
      touchX = null;
    }, { passive: true });

    restart();
  }

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.news-slider').forEach(init);
  });
})();