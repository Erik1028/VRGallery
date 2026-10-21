// The app family: a slim strip at the very top of every app page with all of Erik1028's apps, this one marked, and
// Erik1028 leading to the index. On OrbitOverlay's 1990s homepage (html[data-style="95"]) it is a webring instead:
// « the previous app | Erik1028's webring | the next app ».
// Load it right after <body> (it puts itself where it is, before anything paints, so nothing moves). The same file on
// every app page; the icons are the hub's (erik1028.github.io/img).
(function () {
  var me = document.currentScript;
  if (!me) return;
  var APPS = [
    ['OrbitOverlay', 'OrbitOverlay', 'orbitoverlay.svg'], ['VRGallery', 'VR Gallery', 'vrgallery.png'], ['Mixtape', 'Mixtape', 'mixtape.png'],
    ['ajazz-dock', 'Hexpad', 'hexpad.png'], ['Prisma', 'Prisma', 'prisma.png'], ['Flux', 'Flux', 'flux.png'], ['focal', 'Focal', 'focal.png']
  ];
  var seg = (location.pathname.split('/')[1] || '').toLowerCase(), here = -1;
  APPS.forEach(function (a, i) { if (a[0].toLowerCase() === seg) here = i; });
  var hu = (document.documentElement.lang || '').slice(0, 2) === 'hu';
  var ROOT = 'https://erik1028.github.io/';

  var nav = document.createElement('nav');
  nav.className = 'family';
  nav.setAttribute('aria-label', hu ? 'Erik1028 appjai' : "Erik1028's apps");
  nav.innerHTML = '<div class="fam-in"><a class="fam-home" href="' + ROOT + '">Erik1028</a><span class="fam-sep" aria-hidden="true"></span>' +
    APPS.map(function (a, i) {
      return '<a href="' + ROOT + a[0] + '/"' + (i === here ? ' aria-current="page"' : '') + ' title="' + a[1] + '"><img src="' + ROOT + 'img/' + a[2] +
        '" width="18" height="18" alt=""><span>' + a[1] + '</span></a>';
    }).join('') + '</div>';
  var ring = null;
  if (here >= 0) {
    var prev = APPS[(here + APPS.length - 1) % APPS.length], next = APPS[(here + 1) % APPS.length];
    ring = document.createElement('p');
    ring.className = 'fam-ring';
    ring.innerHTML = '[ <a href="' + ROOT + prev[0] + '/">&laquo; ' + prev[1] + '</a> | <a href="' + ROOT + '">' + (hu ? 'Erik1028 webgyűrűje' : "Erik1028's webring") +
      '</a> | <a href="' + ROOT + next[0] + '/">' + next[1] + ' &raquo;</a> ]';
  }
  me.parentNode.insertBefore(nav, me);
  if (ring) me.parentNode.insertBefore(ring, me);

  var css = document.createElement('style');
  css.textContent =
    '.family{position:relative;z-index:5;background:rgba(9,10,14,.82);-webkit-backdrop-filter:blur(10px);backdrop-filter:blur(10px);border-bottom:1px solid rgba(255,255,255,.08);color:rgba(255,255,255,.72);' +
    'font:500 13.5px/1 "Segoe UI Variable Text","Segoe UI",system-ui,-apple-system,sans-serif}' +
    '.fam-in{max-width:1120px;margin:0 auto;height:40px;display:flex;align-items:center;gap:2px;overflow-x:auto;scrollbar-width:none;' +
    'padding-left:max(14px,env(safe-area-inset-left,0px));padding-right:max(14px,env(safe-area-inset-right,0px))}' +
    '.fam-in::-webkit-scrollbar{display:none}' +
    '.family a{display:inline-flex;align-items:center;gap:7px;flex:none;padding:6px 9px;border-radius:8px;color:inherit;text-decoration:none;white-space:nowrap}' +
    '.family a:hover{background:rgba(255,255,255,.08);color:#fff}' +
    '.family a:focus-visible{outline:2px solid #fff;outline-offset:-2px}' +
    '.family a[aria-current]{background:rgba(255,255,255,.12);color:#fff}' +
    '.family .fam-home{font-weight:700;color:#fff;padding-left:2px}' +
    '.fam-sep{flex:none;width:1px;height:16px;margin:0 6px;background:rgba(255,255,255,.18)}' +
    '.family img{width:18px;height:18px;border-radius:5px;flex:none}' +
    '@media (max-width:899px){.family a:not([aria-current]):not(.fam-home) span{display:none}.family a{padding:6px 7px}}' +
    // a phone: icons only, the current app shown by its highlight, so all seven fit without scrolling
    '@media (max-width:480px){.family a[aria-current] span{display:none}.fam-in{gap:0}.family a{padding:6px}.fam-sep{margin:0 4px}}' +
    '.fam-ring{display:none}' +
    // the 1990s homepage: a webring line instead of today's strip
    'html[data-style="95"] .family{display:none}' +
    'html[data-style="95"] .fam-ring{display:block;margin:0;padding:8px 12px;text-align:center;font:16px/1.4 "Times New Roman",Times,serif;color:#fff}';
  document.head.appendChild(css);
})();
