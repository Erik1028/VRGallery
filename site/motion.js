// Scroll motion, in the spirit of Apple's product pages but light.
//  [data-reveal]      rises in once it comes into view.
//  [data-stagger]     its children rise in one after another (value: ms between them, default 90).
//  [data-scroll]      gets --p: 0 while its top is at the bottom of the window, 1 once it reaches data-end
//                     (a share of the window height from the top, default .4). CSS turns that into movement.
//  :root              gets --sy, the scroll position in px, for the hero pieces.
// Only things that start below the window are ever hidden, and only while they wait to be scrolled to: without
// the script, with reduced motion, and in any first screenshot the page is complete.
(function () {
  var root = document.documentElement;
  if (window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  root.classList.add('motion');
  function vh() { return window.innerHeight || root.clientHeight; }

  Array.prototype.forEach.call(document.querySelectorAll('[data-stagger]'), function (parent) {
    var step = +parent.getAttribute('data-stagger') || 90;
    Array.prototype.forEach.call(parent.children, function (child, i) {
      child.setAttribute('data-reveal', '');
      child.style.setProperty('--d', (i * step) + 'ms');
    });
  });

  function show(el) {
    el.classList.remove('pre');
    el.addEventListener('transitionend', function done(e) {
      if (e.target !== el || e.propertyName !== 'opacity') return;
      el.removeEventListener('transitionend', done);
      el.classList.add('done');                     // later transitions (hover) run without the stagger delay
      el.style.removeProperty('--d');
    });
  }
  if ('IntersectionObserver' in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        io.unobserve(e.target);
        show(e.target);
      });
    }, { rootMargin: '0px 0px -6% 0px', threshold: 0.1 });
    var h = vh();
    Array.prototype.forEach.call(document.querySelectorAll('[data-reveal]'), function (el) {
      if (el.getBoundingClientRect().top > h * 0.94) { el.classList.add('pre'); io.observe(el); }
      else { el.classList.add('done'); el.style.removeProperty('--d'); }   // already in view: nothing to reveal
    });
  }

  var scrubs = Array.prototype.slice.call(document.querySelectorAll('[data-scroll]'));
  var queued = false;
  function frame() {
    queued = false;
    var h = vh();
    root.style.setProperty('--sy', Math.round(window.scrollY));
    scrubs.forEach(function (el) {
      var top = el.getBoundingClientRect().top, end = parseFloat(el.getAttribute('data-end') || '.4') * h;
      var p = (h - top) / Math.max(1, h - end);
      el.style.setProperty('--p', (p < 0 ? 0 : p > 1 ? 1 : p).toFixed(4));
    });
  }
  function queue() { if (!queued) { queued = true; requestAnimationFrame(frame); } }
  addEventListener('scroll', queue, { passive: true });
  addEventListener('resize', queue);
  frame();
})();
