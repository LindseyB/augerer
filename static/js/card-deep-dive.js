/**
 * "Dive deeper" on the card detail page: streams an in-depth AI study of a
 * single card from /stream-deep-reading into the interpretation box.
 */
(function () {
  'use strict';

  var ERROR_HTML =
    '<em style="color:var(--starlight-dim)">The reader is taking a cosmic break. Sit with this card a while. ✨</em>';

  var streamActive = false;
  var fullText = '';

  function configureMarked() {
    if (!window.marked || !window.marked.use || !window.marked.Renderer) return;
    // Strip raw HTML blocks so AI output injected into innerHTML cannot XSS.
    var safeRenderer = new window.marked.Renderer();
    safeRenderer.html = function () { return ''; };
    window.marked.use({ renderer: safeRenderer });
  }

  function copyText(text, btn) {
    function done() {
      btn.textContent = 'Copied!';
      setTimeout(function () { btn.textContent = 'Copy reading'; }, 2000);
    }
    function fallback() {
      try {
        var area = document.createElement('textarea');
        area.value = text;
        area.style.position = 'fixed';
        area.style.left = '-9999px';
        document.body.appendChild(area);
        area.select();
        document.execCommand('copy');
        document.body.removeChild(area);
        done();
      } catch (e) { /* silent */ }
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done).catch(fallback);
    } else {
      fallback();
    }
  }

  function init() {
    var section = document.getElementById('deepDive');
    var btn = document.getElementById('deepDiveBtn');
    if (!section || !btn) return;

    configureMarked();

    var resultBox = document.getElementById('deepDiveResult');
    var contentEl = document.getElementById('deepDiveContent');
    var indicator = document.getElementById('deepDiveIndicator');
    var copyBtn = document.getElementById('deepDiveCopyBtn');
    var slug = section.dataset.slug;
    var orientation = section.dataset.orientation || '';
    var cardName = section.dataset.cardName || '';

    function finalize(isError) {
      streamActive = false;
      if (indicator) indicator.hidden = true;
      contentEl.setAttribute('aria-busy', 'false');
      contentEl.style.whiteSpace = 'normal';

      if (isError || !fullText) {
        // Let the querent try again if the reader couldn't come through.
        btn.disabled = false;
        btn.innerHTML = '<span class="moon-icon" aria-hidden="true"></span> Dive deeper';
        contentEl.innerHTML = ERROR_HTML;
        return;
      }

      btn.hidden = true;

      if (window.marked && window.marked.parse) {
        contentEl.innerHTML = window.marked.parse(fullText);
      } else {
        contentEl.textContent = fullText;
      }

      if (copyBtn) {
        var label = cardName + (orientation ? ' (' + orientation + ')' : '');
        var copyContent = 'Deep dive: ' + label + '\n\n' + fullText.trim();
        copyBtn.hidden = false;
        copyBtn.onclick = function () { copyText(copyContent, copyBtn); };
      }
    }

    function start() {
      if (streamActive) return;
      streamActive = true;
      fullText = '';

      btn.disabled = true;
      btn.textContent = 'Gazing deeper…';
      resultBox.hidden = false;
      resultBox.classList.add('animate-fade-in');
      if (copyBtn) copyBtn.hidden = true;
      contentEl.innerHTML = '';
      contentEl.style.whiteSpace = 'pre-wrap';
      contentEl.setAttribute('aria-busy', 'true');
      if (indicator) indicator.hidden = false;

      setTimeout(function () {
        resultBox.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }, 100);

      fetch('/stream-deep-reading', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ slug: slug, orientation: orientation })
      }).then(function (response) {
        if (!response.ok) { finalize(true); return; }

        var reader = response.body.getReader();
        var decoder = new TextDecoder();
        var buffer = '';

        function pump() {
          reader.read().then(function (result) {
            if (result.done) { finalize(false); return; }

            buffer += decoder.decode(result.value, { stream: true });
            var lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (var i = 0; i < lines.length; i++) {
              var line = lines[i];
              if (line.indexOf('data: ') !== 0) continue;
              try {
                var data = JSON.parse(line.substring(6));
                if (data.chunk) {
                  fullText += data.chunk;
                  contentEl.textContent = fullText;
                } else if (data.done) {
                  finalize(false);
                  return;
                } else if (data.error) {
                  finalize(true);
                  return;
                }
              } catch (e) { /* skip bad JSON */ }
            }

            pump();
          }).catch(function () { finalize(true); });
        }

        pump();
      }).catch(function () { finalize(true); });
    }

    btn.addEventListener('click', start);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
}());
