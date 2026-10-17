// For visitors who can't install from where they are. The apps go on a PC, but many people find them on a phone or in
// a headset's browser: on a phone, a note above the download button with "Send the link" (the phone's share sheet) and
// "Copy link"; in a headset, the address to open on the PC. On Linux, a page with an AppImage puts that first.
// On OrbitOverlay's 1990s homepage (html[data-style="95"], win95.js) the note is a 1990s one too, in words and looks,
// and it changes over when the page does (the 'orbit-style' event).
// The same file on every app page (Erik1028's apps); the app's name comes from og:title. ?as=phone|headset|linux shows a case.
(function () {
  var get = document.querySelector('.get'), btn = get && get.querySelector('.btn');
  if (!btn) return;
  var ua = navigator.userAgent || '', as = (location.search.match(/[?&]as=(\w+)/) || [])[1];
  var headset = as ? as === 'headset' : /OculusBrowser|Quest|Pico|Wolvic/i.test(ua);
  var phone = as ? as === 'phone' : !headset && (/Android|iPhone|iPad|iPod|Mobile/i.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1));
  var linux = as ? as === 'linux' : !headset && !phone && /Linux|X11/.test(ua);
  var hu = (document.documentElement.lang || '').slice(0, 2) === 'hu';
  var og = document.querySelector('meta[property="og:title"]');
  var app = (og && og.content) || document.title.split(' · ')[0];
  var canon = document.querySelector('link[rel="canonical"]');
  var url = (canon && canon.href) || location.href.split(/[?#]/)[0];
  var shortUrl = url.replace(/^https?:\/\//, '').replace(/\/$/, '');

  if (linux) {
    var img = document.querySelector('a[data-asset*="AppImage"]');
    if (img && img !== btn) {
      btn.href = img.href;
      btn.setAttribute('data-asset', img.getAttribute('data-asset'));   // site.js points it at the latest AppImage
      if (btn.lastChild) btn.lastChild.textContent = 'Download the Linux AppImage';
    }
    return;
  }
  if (!phone && !headset) return;

  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  var az = /^[aeiouáéíóöőúüű]/i.test(app) ? 'Az ' : 'A ', a = esc(app), u = '<span class="ho-url">' + esc(shortUrl) + '</span>';
  // today's words, and a 1990s homepage's (when people "surfed the Web" and a phone browsing it was the future)
  var T = hu ? {
    now: { head: headset ? 'A headsetben vagy?' : 'Telefonról nézed?',
      text: headset ? az + a + ' a számítógépre kerül. Nyisd meg ott ezt az oldalt: ' + u : az + a + ' a számítógépeden fut. Küldd el magadnak a linket, és nyisd meg ott.',
      share: 'Link küldése', copy: 'Link másolása', copied: 'Kimásolva' },
    old: { head: '!!! FIGYELEM !!!',
      text: headset ? 'A virtuális valóságból szörfözöl? A jövő már itt van! ' + az + a + ' a PC-dre való: nyisd meg ott ezt a címet: ' + u
        : 'Úgy látom, mobiltelefonról szörfözöl! ' + az + a + ' a PC-dre való. Küldd el magadnak a címet, és nyisd meg otthon, a számítógépen!',
      share: 'Elküldöm magamnak!', copy: 'Cím másolása', copied: 'Kimásolva!' },
    shareText: 'letöltés a gépemre'
  } : {
    now: { head: headset ? 'In your headset?' : 'On your phone?',
      text: headset ? a + ' goes on your PC. Open this page there: ' + u : a + ' runs on your PC. Send yourself the link and open it there.',
      share: 'Send the link', copy: 'Copy link', copied: 'Copied' },
    old: { head: '!!! ATTENTION !!!',
      text: headset ? 'Surfing the Web from virtual reality? The future is here! ' + a + ' is for your PC: open this address there: ' + u
        : 'Looks like you are surfing the Web on a mobile phone! ' + a + ' is for your PC. Send yourself the address and open it on your home computer!',
      share: 'Send it to me!', copy: 'Copy the address', copied: 'Copied!' },
    shareText: 'to download on my PC'
  };
  var canShare = phone && typeof navigator.share === 'function';
  var ICON = headset
    ? '<svg class="ho-ic" width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" aria-hidden="true"><path d="M3 9a3 3 0 0 1 3-3h12a3 3 0 0 1 3 3v5a3 3 0 0 1-3 3h-3l-2-2.5h-2L9 17H6a3 3 0 0 1-3-3z"/><circle cx="8" cy="11.5" r="1.6"/><circle cx="16" cy="11.5" r="1.6"/></svg>'
    : '<svg class="ho-ic" width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="2" y="9" width="7" height="12" rx="1.6"/><path d="M5 18h1"/><rect x="11" y="3" width="11" height="8" rx="1"/><path d="M14 15h5M16.5 11v4"/><path d="M4 6.5C5 4.5 7 3.5 9 3.5"/></svg>';
  // the 1990s note's picture: a pixel mobile phone with its aerial (or, in a headset, pixel VR goggles)
  var PIX = headset
    ? '<svg class="ho-ic" width="48" height="24" viewBox="0 0 24 12" shape-rendering="crispEdges" aria-hidden="true"><path d="M2 2h20v8h-7v-2h-6v2H2z" fill="#c0c0c0"/><path d="M2 2h20v1H2zM2 2h1v8H2z" fill="#fff"/><path d="M4 4h6v3H4zM14 4h6v3h-6z" fill="#0ff"/><path d="M4 4h6v1H4zM14 4h6v1h-6z" fill="#08f"/><path d="M0 4h2v2H0zM22 4h2v2h-2z" fill="#808080"/></svg>'
    : '<svg class="ho-ic" width="24" height="44" viewBox="0 0 12 22" shape-rendering="crispEdges" aria-hidden="true"><path d="M8 0h1v5H8z" fill="#808080"/><path d="M2 5h8v17H2z" fill="#c0c0c0"/><path d="M2 5h8v1H2zM2 5h1v17H2z" fill="#fff"/><path d="M3 7h6v5H3z" fill="#7f9f3f"/><path d="M4 8h4v1H4zM4 10h3v1H4z" fill="#203010"/><path d="M3 14h1v1H3zM5 14h1v1H5zM7 14h1v1H7zM3 16h1v1H3zM5 16h1v1H5zM7 16h1v1H7zM3 18h1v1H3zM5 18h1v1H5zM7 18h1v1H7z" fill="#000"/></svg>';

  var box = document.createElement('div');
  box.setAttribute('role', 'note');
  get.insertBefore(box, btn);
  var words;
  function render() {
    var old = document.documentElement.getAttribute('data-style') === '95';
    words = old ? T.old : T.now;
    box.className = 'handoff' + (old ? ' ho-old' : '');
    box.innerHTML = (old ? PIX : ICON) + '<div><p><b class="ho-head">' + words.head + '</b> ' + words.text + '</p>' +
      '<div class="ho-btns">' + (canShare ? '<button type="button" class="ho-share">' + words.share + '</button>' : '') +
      '<button type="button" class="ho-copy">' + words.copy + '</button></div></div>';
  }
  render();
  document.addEventListener('orbit-style', render);

  function copied(b) {
    b.textContent = words.copied;
    setTimeout(function () { if (b.isConnected) b.textContent = words.copy; }, 1800);
  }
  function fallbackCopy(b) {
    var t = document.createElement('textarea');
    t.value = url; t.setAttribute('readonly', ''); t.style.position = 'fixed'; t.style.opacity = '0';
    document.body.appendChild(t); t.select();
    try { if (document.execCommand('copy')) copied(b); } catch (e) {}
    document.body.removeChild(t);
  }
  box.addEventListener('click', function (e) {
    var b = e.target.closest('button');
    if (!b) return;
    if (b.classList.contains('ho-copy')) {
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(url).then(function () { copied(b); }, function () { fallbackCopy(b); });
      else fallbackCopy(b);
    } else if (b.classList.contains('ho-share')) {
      navigator.share({ title: app, text: app + ' · ' + T.shareText, url: url }).catch(function () {});
    }
  });

  var css = document.createElement('style');
  css.textContent =
    '.handoff{display:flex;gap:12px;align-items:flex-start;max-width:31em;padding:12px 14px;border-radius:12px;background:rgba(0,0,0,.22);' +
    'border:1px solid rgba(255,255,255,.15);font-size:15px;line-height:1.45;text-align:left;color:inherit}' +
    '.handoff .ho-ic{flex:none;margin-top:1px;opacity:.9}.handoff p{margin:0}.handoff b{font-weight:700}' +
    '.handoff .ho-url{font-family:var(--mono,monospace);font-size:.92em;overflow-wrap:anywhere}' +
    '.handoff .ho-btns{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}' +
    '.handoff button{font:inherit;font-size:14.5px;font-weight:600;color:inherit;background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.24);' +
    'border-radius:9px;padding:0 14px;min-height:42px;cursor:pointer}' +
    '.handoff .ho-share{background:var(--accent,#fff);color:var(--on-accent,#111);border-color:transparent}' +
    // the 1990s note: a navy box with a ridge border, Times, a blinking warning, grey 3D buttons, a pixel picture
    '.handoff.ho-old{flex-direction:column;align-items:center;gap:8px;max-width:30em;margin:0 auto;padding:12px 16px 16px;border-radius:0;background:#000080;' +
    'border:4px ridge #c0c0c0;color:#fff;font-family:"Times New Roman",Times,serif;font-size:17px;line-height:1.4;text-align:center}' +
    '.handoff.ho-old .ho-ic{opacity:1;margin:0;image-rendering:pixelated}' +
    '.handoff.ho-old .ho-head{display:table;margin:0 auto 6px;padding:0 6px;background:#ff0;color:#f00;font:900 15px/1.4 Arial,sans-serif;animation:hoBlink 1s steps(1) infinite}' +
    '.handoff.ho-old .ho-url{display:inline-block;font-family:"Courier New",Courier,monospace;font-size:15px;color:#ff0}' +
    '.handoff.ho-old .ho-btns{justify-content:center;margin-top:12px}' +
    '.handoff.ho-old button{border:0;border-radius:0;background:#c0c0c0;color:#000;font:700 15px Arial,sans-serif;padding:0 16px;min-height:40px;' +
    'box-shadow:inset -1px -1px #0a0a0a,inset 1px 1px #fff,inset -2px -2px #808080,inset 2px 2px #dfdfdf}' +
    '.handoff.ho-old button:active{box-shadow:inset -1px -1px #fff,inset 1px 1px #808080,inset -2px -2px #dfdfdf,inset 2px 2px #0a0a0a}' +
    '.handoff.ho-old button:focus-visible{outline:1px dotted #000;outline-offset:-5px}' +
    '@keyframes hoBlink{50%{visibility:hidden}}@media (prefers-reduced-motion:reduce){.handoff.ho-old .ho-head{animation:none}}';
  document.head.appendChild(css);
})();
