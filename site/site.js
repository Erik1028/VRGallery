// The latest release from GitHub: version, date, the right download links and a short "latest update".
// <body data-repo="owner/name">; links with data-asset="regex" point at the matching file of the latest release.
// Everything here is optional: the HTML carries the version, sizes and latest update as of the last edit, so a
// failed or rate-limited request (GitHub allows 60 an hour per visitor) leaves those in place.
(function () {
  var repo = document.body.getAttribute('data-repo');
  if (!repo) return;
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function mb(n) { return n >= 1048576 * 10 ? Math.round(n / 1048576) + ' MB' : (Math.round(n / 104857.6) / 10) + ' MB'; }
  fetch('https://api.github.com/repos/' + repo + '/releases?per_page=10')
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (list) {
      if (!list) return;
      var rel = list.filter(function (x) { return !x.draft && !x.prerelease; })[0];
      if (!rel) return;
      var date = rel.published_at ? new Date(rel.published_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '';
      var ver = document.getElementById('ver');
      if (ver) ver.textContent = rel.tag_name + (date ? ' · ' + date : '');
      Array.prototype.forEach.call(document.querySelectorAll('[data-asset]'), function (a) {
        var re = new RegExp(a.getAttribute('data-asset'), 'i');
        var asset = (rel.assets || []).filter(function (x) { return re.test(x.name); })[0];
        if (!asset) return;
        a.href = asset.browser_download_url;
        var size = a.querySelector('.size');
        if (size) size.textContent = ' (' + mb(asset.size) + ')';
      });
      var box = document.getElementById('latest');
      if (box) {
        var name = (rel.name || rel.tag_name).replace(/^[^—–-]*[—–-]\s*/, '') || rel.name;
        name = name.charAt(0).toUpperCase() + name.slice(1);
        // the first paragraph of the notes. Release notes are hard-wrapped, so its lines are joined; a list item
        // keeps its wrapped continuation lines and ends at the next item. Headings, tables, quotes, a line that is
        // only a bold title, and the list of downloads (`file` items) are skipped.
        var para = [], lines = (rel.body || '').split(/\r?\n/).map(function (l) { return l.trim(); });
        for (var i = 0; i < lines.length; i++) {
          var l = lines[i];
          if (!l || /^(#|\||>)/.test(l) || /^\*\*[^*]+\*\*$/.test(l)) { if (para.length) break; continue; }
          if (/^[-*]\s*`/.test(l)) { if (para.length) break; continue; }
          if (/^[-*]\s+/.test(l) && para.length) break;
          para.push(l);
        }
        var first = para.join(' ');
        first = first.replace(/^[-*]\s+/, '').replace(/\*\*(.+?)\*\*/g, '$1').replace(/`(.+?)`/g, '$1').replace(/\[(.+?)\]\(.+?\)/g, '$1').replace(/\*+/g, '');
        if (first.length > 220) first = first.slice(0, 217).replace(/\s+\S*$/, '') + '…';
        box.innerHTML = '<span class="v">' + esc(rel.tag_name) + '</span><div><h3>' + esc(name) + '</h3>' +
          (first ? '<p>' + esc(first) + '</p>' : '') +
          '<p><a href="' + esc(rel.html_url) + '">Release notes</a> · ' + esc(date) + '</p></div>';
      }
    })
    .catch(function () {});
  // screenshot slots: shown once the file exists (img/NAME.png)
  Array.prototype.forEach.call(document.querySelectorAll('[data-slot]'), function (fig) {
    var src = fig.getAttribute('data-slot');
    fetch(src, { method: 'HEAD' }).then(function (r) {
      if (!r.ok) return;
      var img = new Image();
      img.src = src; img.alt = fig.getAttribute('data-alt') || '';
      fig.querySelector('.shot').appendChild(img);
      fig.hidden = false;
    }).catch(function () {});
  });
})();
