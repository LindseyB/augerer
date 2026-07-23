(function () {
  'use strict';

  var spread = window.readingSpread;
  var drawn = null;
  var fullText = '';
  var currentQuestion = '';
  var streamActive = false;

  var CARD_BACK_HTML =
    '<div class="card-back">' +
      '<svg class="card-back-pentagram" viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">' +
        '<circle cx="100" cy="100" r="94" fill="none" stroke="currentColor" stroke-width="3"/>' +
        '<circle cx="100" cy="100" r="83" fill="none" stroke="currentColor" stroke-width="11"/>' +
        '<path d="M100,30 L141,157 L33,78 L167,78 L59,157 Z" fill="currentColor"/>' +
      '</svg>' +
      '<div class="card-back-shimmer"></div>' +
      '<p class="card-back-label">Aether &amp; Arcana</p>' +
    '</div>';

  function escHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function buildCopyText(drawnCards, question, reading) {
    var lines = [];
    if (question) {
      lines.push('Question: ' + question, '');
    }

    if (Array.isArray(drawnCards) && drawnCards.length) {
      lines.push(drawnCards.length > 1 ? 'Cards pulled:' : 'Card pulled:');
      drawnCards.forEach(function (entry) {
        var label = entry.position ? entry.position + ': ' : '';
        var orientation = entry.orientation === 'reversed' ? ' (reversed)' : ' (upright)';
        lines.push('- ' + label + entry.card.name + orientation);

        var meanings = entry.card.meanings || {};
        var cues = (entry.orientation === 'reversed' ? meanings.reversed : meanings.upright) || [];
        if (Array.isArray(cues) && cues.length) {
          lines.push('  Keywords: ' + cues.slice(0, 3).join(', '));
        }
      });
      lines.push('');
    }

    lines.push('Reading:');
    lines.push(reading.trim());
    return lines.join('\n');
  }

  function cardImageUrl(slug, orientation) {
    return '/card-image/' + encodeURIComponent(slug) + '.svg?orientation=' + orientation + '&mode=dark';
  }

  function resetCards() {
    var n = spread === 'three' ? 3 : 1;
    for (var i = 0; i < n; i++) {
      var visual = document.getElementById('cardVisual' + i);
      if (visual) {
        visual.innerHTML = CARD_BACK_HTML;
        visual.classList.remove('reversed', 'animate-card-rise');
      }
      var nameEl = document.getElementById('cardName' + i);
      if (nameEl) nameEl.textContent = '';

      var orientEl = document.getElementById('cardOrient' + i);
      if (orientEl) {
        orientEl.textContent = '';
        orientEl.className = spread === 'three' ? 'spread-card-orientation' : 'card-orientation';
      }

      var kwEl = document.getElementById('cardKeywords' + i);
      if (kwEl) kwEl.innerHTML = '';
    }

    fullText = '';
    var contentEl = document.getElementById('interpretationContent');
    if (contentEl) { contentEl.innerHTML = ''; contentEl.style.whiteSpace = 'pre-wrap'; }

    var copyBtn = document.getElementById('copyBtn');
    if (copyBtn) {
      copyBtn.hidden = true;
      copyBtn.textContent = 'Copy reading';
    }

    currentQuestion = '';

    var qWrap = document.getElementById('questionEchoWrap');
    if (qWrap) qWrap.hidden = true;

    var indicator = document.getElementById('streamingIndicator');
    if (indicator) indicator.hidden = true;
  }

  function revealCard(i, entry, delay) {
    setTimeout(function () {
      var visual = document.getElementById('cardVisual' + i);
      if (!visual) return;

      var link = document.getElementById('cardLink' + i);
      if (link) {
        link.href = '/card/' + encodeURIComponent(entry.card.slug);
        link.setAttribute('aria-label', 'Read more about ' + entry.card.name);
      }

      var img = document.createElement('img');
      img.src = cardImageUrl(entry.card.slug, entry.orientation);
      img.alt = escHtml(entry.card.name) + ' tarot card';

      visual.innerHTML = '';
      visual.appendChild(img);

      if (entry.orientation === 'reversed') visual.classList.add('reversed');
      void visual.offsetWidth;
      visual.classList.add('animate-card-rise');

      var nameEl = document.getElementById('cardName' + i);
      if (nameEl) nameEl.textContent = entry.card.name;

      var orientEl = document.getElementById('cardOrient' + i);
      if (orientEl) {
        orientEl.textContent = entry.orientation;
        if (entry.orientation === 'reversed') orientEl.classList.add('reversed');
      }

      var kwEl = document.getElementById('cardKeywords' + i);
      if (kwEl) renderKeywords(kwEl, entry.card.meanings, entry.orientation);
    }, delay || 0);
  }

  function renderKeywords(el, meanings, orientation) {
    var kw = (orientation === 'reversed' ? meanings.reversed : meanings.upright) || meanings.upright || [];
    el.innerHTML = kw.slice(0, 3).map(function (word) {
      var cls = orientation === 'reversed' ? 'keyword-badge reversed' : 'keyword-badge';
      return '<li><span class="' + cls + '">' + escHtml(word) + '</span></li>';
    }).join('');
  }

  function startStreaming(cards, question) {
    if (streamActive) return;
    streamActive = true;

    var contentEl = document.getElementById('interpretationContent');
    var indicator = document.getElementById('streamingIndicator');

    if (contentEl) { contentEl.innerHTML = ''; contentEl.style.whiteSpace = 'pre-wrap'; }
    if (indicator) indicator.hidden = false;

    var payload = {
      spread: spread,
      question: question || '',
      cards: cards.map(function (c) {
        return { slug: c.card.slug, orientation: c.orientation, position: c.position || '' };
      })
    };

    fetch('/stream-reading', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }).then(function (response) {
      if (!response.ok) {
        finalize(true);
        return;
      }

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
                if (contentEl) contentEl.textContent = fullText;
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

  function finalize(isError) {
    streamActive = false;
    var drawBtn = document.getElementById('drawBtn');
    if (drawBtn) {
      drawBtn.disabled = false;
      drawBtn.textContent = spread === 'three' ? 'Cast again' : 'Draw again';
    }
    var contentEl = document.getElementById('interpretationContent');
    var indicator = document.getElementById('streamingIndicator');
    var copyBtn = document.getElementById('copyBtn');

    if (indicator) indicator.hidden = true;

    if (isError) {
      if (contentEl) {
        contentEl.style.whiteSpace = 'normal';
        contentEl.innerHTML = '<em style="color:var(--starlight-dim)">The reader is taking a cosmic break. Sit with your cards. ✨</em>';
      }
      return;
    }

    if (contentEl && fullText) {
      contentEl.style.whiteSpace = 'normal';
      if (window.marked && window.marked.parse) {
        contentEl.innerHTML = window.marked.parse(fullText);
      } else {
        contentEl.textContent = fullText;
      }
    }

    if (copyBtn) {
      var copyContent = buildCopyText(drawn, currentQuestion, fullText);
      copyBtn.hidden = false;
      copyBtn.onclick = function () {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(copyContent).then(function () {
            copyBtn.textContent = 'Copied!';
            setTimeout(function () { copyBtn.textContent = 'Copy reading'; }, 2000);
          }).catch(function () { fallbackCopy(copyContent, copyBtn); });
        } else {
          fallbackCopy(copyContent, copyBtn);
        }
      };
    }
  }

  function fallbackCopy(text, btn) {
    try {
      var area = document.createElement('textarea');
      area.value = text;
      area.style.position = 'fixed';
      area.style.left = '-9999px';
      document.body.appendChild(area);
      area.select();
      document.execCommand('copy');
      document.body.removeChild(area);
      if (btn) {
        btn.textContent = 'Copied!';
        setTimeout(function () { btn.textContent = 'Copy reading'; }, 2000);
      }
    } catch (e) { /* silent */ }
  }

  function configureMarked() {
    if (!window.marked || !window.marked.use || !window.marked.Renderer) return;
    // Strip raw HTML blocks so AI output injected into innerHTML cannot XSS.
    var safeRenderer = new window.marked.Renderer();
    safeRenderer.html = function () { return ''; };
    window.marked.use({ renderer: safeRenderer });
  }

  function handleDraw() {
    if (streamActive) return;

    var drawBtn = document.getElementById('drawBtn');
    var qInput = document.getElementById('questionInput');
    var question = qInput ? qInput.value.trim() : '';
    currentQuestion = question;

    if (drawBtn) {
      drawBtn.disabled = true;
      drawBtn.textContent = spread === 'three' ? 'Casting…' : 'Drawing…';
    }

    var n = spread === 'three' ? 3 : 1;

    // If already shown, reset first
    var resultSection = document.getElementById('resultSection');
    if (resultSection && !resultSection.hidden) {
      resetCards();
    }

    fetch('/api/spread?n=' + n)
      .then(function (r) {
        if (!r.ok) throw new Error('spread API error');
        return r.json();
      })
      .then(function (data) {
        drawn = data.cards;

        // Show result section
        if (resultSection) {
          resultSection.hidden = false;
          resultSection.classList.add('animate-fade-in');
        }

        // Show question echo
        if (question) {
          var qWrap = document.getElementById('questionEchoWrap');
          var qEcho = document.getElementById('questionEcho');
          if (qEcho) qEcho.textContent = '“' + question + '”';
          if (qWrap) qWrap.hidden = false;
        }

        // Reveal cards (staggered for three-card)
        drawn.forEach(function (entry, i) {
          revealCard(i, entry, spread === 'three' ? i * 220 : 0);
        });

        // Start streaming after brief pause for card reveal animation.
        // Button stays disabled until finalize() re-enables it, closing the
        // race window where a second click could launch a concurrent draw.
        var streamDelay = spread === 'three' ? 700 : 200;
        setTimeout(function () {
          startStreaming(drawn, question);
        }, streamDelay);

        // Scroll to results
        if (resultSection) {
          setTimeout(function () {
            resultSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
          }, 100);
        }
      })
      .catch(function () {
        if (drawBtn) {
          drawBtn.disabled = false;
          drawBtn.textContent = spread === 'three' ? 'Cast the spread' : 'Draw a card';
        }
      });
  }

  function init() {
    configureMarked();
    var drawBtn = document.getElementById('drawBtn');
    if (drawBtn) drawBtn.addEventListener('click', handleDraw);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
}());
