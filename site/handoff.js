// For visitors who can't install from where they are. The apps go on a PC, but many people find them on a phone or in
// a headset's browser: on a phone, a note above the download button with "Send the link" (the phone's share sheet) and
// "Copy link"; in a headset, the address to open on the PC. On Linux, a page with an AppImage puts that first.
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
  var az = /^[aeiouáéíóöőúüű]/i.test(app) ? 'Az ' : 'A ';
  var T = hu ? {
    phoneHead: 'Telefonról nézed?', phone: az + esc(app) + ' a számítógépeden fut. Küldd el magadnak a linket, és nyisd meg ott.',
    vrHead: 'A headsetben vagy?', vr: az + esc(app) + ' a számítógépre kerül. Nyisd meg ott ezt az oldalt:',
    share: 'Link küldése', copy: 'Link másolása', copied: 'Kimásolva', shareText: 'letöltés a gépemre'
  } : {
    phoneHead: 'On your phone?', phone: esc(app) + ' runs on your PC. Send yourself the link and open it there.',
    vrHead: 'In your headset?', vr: esc(app) + ' goes on your PC. Open this page there:',
    share: 'Send the link', copy: 'Copy link', copied: 'Copied', shareText: 'to download on my PC'
  };
  var canShare = phone && typeof navigator.share === 'function';
  var icon = headset
    ? '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" aria-hidden="true"><path d="M3 9a3 3 0 0 1 3-3h12a3 3 0 0 1 3 3v5a3 3 0 0 1-3 3h-3l-2-2.5h-2L9 17H6a3 3 0 0 1-3-3z"/><circle cx="8" cy="11.5" r="1.6"/><circle cx="16" cy="11.5" r="1.6"/></svg>'
    : '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="2" y="9" width="7" height="12" rx="1.6"/><path d="M5 18h1"/><rect x="11" y="3" width="11" height="8" rx="1"/><path d="M14 15h5M16.5 11v4"/><path d="M4 6.5C5 4.5 7 3.5 9 3.5"/></svg>';
  var box = document.createElement('div');
  box.className = 'handoff';
  box.setAttribute('role', 'note');
  box.innerHTML = icon + '<div><p><b>' + (headset ? T.vrHead : T.phoneHead) + '</b> ' + (headset ? T.vr + ' <span class="ho-url">' + esc(shortUrl) + '</span>' : T.phone) + '</p>' +
    '<div class="ho-btns">' + (canShare ? '<button type="button" class="ho-share">' + T.share + '</button>' : '') +
    '<button type="button" class="ho-copy">' + T.copy + '</button></div></div>';
  get.insertBefore(box, btn);

  var copyBtn = box.querySelector('.ho-copy');
  function copied() {
    copyBtn.textContent = T.copied;
    setTimeout(function () { copyBtn.textContent = T.copy; }, 1800);
  }
  function fallbackCopy() {
    var t = document.createElement('textarea');
    t.value = url; t.setAttribute('readonly', ''); t.style.position = 'fixed'; t.style.opacity = '0';
    document.body.appendChild(t); t.select();
    try { if (document.execCommand('copy')) copied(); } catch (e) {}
    document.body.removeChild(t);
  }
  copyBtn.addEventListener('click', function () {
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(url).then(copied, fallbackCopy);
    else fallbackCopy();
  });
  var shareBtn = box.querySelector('.ho-share');
  if (shareBtn) shareBtn.addEventListener('click', function () {
    navigator.share({ title: app, text: app + ' · ' + T.shareText, url: url }).catch(function () {});
  });

  var css = document.createElement('style');
  css.textContent =
    '.handoff{display:flex;gap:12px;align-items:flex-start;max-width:31em;padding:12px 14px;border-radius:12px;background:rgba(0,0,0,.22);' +
    'border:1px solid rgba(255,255,255,.15);font-size:15px;line-height:1.45;text-align:left;color:inherit}' +
    '.handoff svg{flex:none;margin-top:1px;opacity:.9}.handoff p{margin:0}.handoff b{font-weight:700}' +
    '.handoff .ho-url{font-family:var(--mono,monospace);font-size:.92em;overflow-wrap:anywhere}' +
    '.handoff .ho-btns{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}' +
    '.handoff button{font:inherit;font-size:14.5px;font-weight:600;color:inherit;background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.24);' +
    'border-radius:9px;padding:0 14px;min-height:42px;cursor:pointer}' +
    '.handoff .ho-share{background:var(--accent,#fff);color:var(--on-accent,#111);border-color:transparent}';
  document.head.appendChild(css);
})();
