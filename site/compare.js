// Before and after: the range input (it covers the picture, so a drag anywhere moves it; keys work too) sets --x,
// where VR Gallery's side begins. Without the script the picture stays split down the middle.
(function () {
  var fig = document.getElementById('ba'), range = fig && fig.querySelector('.ba-range');
  if (!range) return;
  function set() { fig.style.setProperty('--x', range.value + '%'); }
  range.addEventListener('input', set);
  set();
  // once, as it comes into view: a short sweep that shows it can be dragged
  if (!('IntersectionObserver' in window) || (window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches)) return;
  var io = new IntersectionObserver(function (es) {
    if (!es[0].isIntersecting) return;
    io.disconnect();
    var t0 = performance.now();
    (function step(t) {
      var k = Math.min(1, (t - t0) / 1400), v = 50 + Math.sin(k * Math.PI * 2) * 14 * (1 - k);
      if (document.activeElement !== range) { range.value = v.toFixed(1); set(); }
      if (k < 1) requestAnimationFrame(step);
    })(t0);
  }, { threshold: 0.6 });
  io.observe(fig);
})();
