/**
 * Client-side streaming for tarot readings.
 * Adapted from the astro project's stream-analysis.js.
 * Reads window.readingData, POSTs the drawn cards to /stream-reading, and
 * renders the AI response as it streams in.
 */
(function () {
  'use strict';

  var STREAMING_INDICATOR_MARKUP =
    '<span class="streaming-indicator__icon" aria-hidden="true">\u2726</span>' +
    '<div class="streaming-indicator__bars" aria-hidden="true">' +
    '<span class="streaming-indicator__bar"></span>' +
    '<span class="streaming-indicator__bar"></span>' +
    '<span class="streaming-indicator__bar"></span>' +
    '<span class="streaming-indicator__bar"></span>' +
    '</div>' +
    '<span class="sr-only">More content is still streaming in</span>';

  var FALLBACK_HTML =
    '<p>\u2615 The reader is taking a cosmic tea break. Sit with your cards and trust your intuition. \uD83D\uDD2E</p>';

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initStreaming);
  } else {
    initStreaming();
  }

  function initStreaming() {
    if (document.body.dataset.streaming !== 'true') return;

    var analysisContainer = document.getElementById('analysisContent');
    var readingData = window.readingData;
    if (!analysisContainer || !readingData) return;

    var streamedContent = document.getElementById('analysisStreamContent');
    if (!streamedContent) {
      streamedContent = document.createElement('div');
      streamedContent.id = 'analysisStreamContent';
      streamedContent.className = 'streaming-analysis-text';
      analysisContainer.insertBefore(streamedContent, analysisContainer.firstChild);
    }

    var indicator = document.getElementById('analysisStreamIndicator');
    if (!indicator) {
      indicator = document.createElement('div');
      indicator.id = 'analysisStreamIndicator';
      indicator.className = 'streaming-indicator';
      indicator.innerHTML = STREAMING_INDICATOR_MARKUP;
      analysisContainer.appendChild(indicator);
    } else if (!indicator.querySelector('.streaming-indicator__bars')) {
      indicator.removeAttribute('aria-hidden');
      indicator.innerHTML = STREAMING_INDICATOR_MARKUP;
    }

    analysisContainer.setAttribute('aria-busy', 'true');
    streamedContent.textContent = '';
    streamedContent.style.whiteSpace = 'pre-wrap';

    var fullText = '';
    var finalized = false;
    var copyButton = document.getElementById('copyReadingBtn');
    var copyResetTimer = null;

    function setupCopyButton() {
      if (!copyButton || !fullText.trim()) return;
      copyButton.hidden = false;
      copyButton.onclick = function () {
        copyText(fullText).then(function (ok) {
          showCopyFeedback(ok ? 'Copied!' : 'Copy failed');
        });
      };
    }

    function showCopyFeedback(message) {
      var label = copyButton.querySelector('.reading-copy-btn__label');
      if (!label) return;
      if (copyResetTimer) clearTimeout(copyResetTimer);
      var previous = label.getAttribute('data-default') || 'Copy';
      label.setAttribute('data-default', previous);
      label.textContent = message;
      copyButton.classList.add('is-copied');
      copyResetTimer = setTimeout(function () {
        label.textContent = previous;
        copyButton.classList.remove('is-copied');
      }, 2000);
    }

    function copyText(text) {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        return navigator.clipboard.writeText(text).then(
          function () { return true; },
          function () { return legacyCopy(text); }
        );
      }
      return Promise.resolve(legacyCopy(text));
    }

    function legacyCopy(text) {
      try {
        var area = document.createElement('textarea');
        area.value = text;
        area.setAttribute('readonly', '');
        area.style.position = 'absolute';
        area.style.left = '-9999px';
        document.body.appendChild(area);
        area.select();
        var ok = document.execCommand('copy');
        document.body.removeChild(area);
        return ok;
      } catch (e) {
        return false;
      }
    }

    function finalize() {
      if (finalized) return;
      finalized = true;
      if (window.marked && fullText) {
        streamedContent.innerHTML = window.marked.parse(fullText);
      } else {
        streamedContent.textContent = fullText;
      }
      streamedContent.style.whiteSpace = 'normal';
      if (indicator && indicator.parentNode) {
        indicator.parentNode.removeChild(indicator);
      }
      analysisContainer.setAttribute('aria-busy', 'false');
      setupCopyButton();
    }

    function showError() {
      analysisContainer.innerHTML = FALLBACK_HTML;
      analysisContainer.setAttribute('aria-busy', 'false');
    }

    fetch('/stream-reading', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ spread: readingData.spread, cards: readingData.cards })
    })
      .then(function (response) {
        if (!response.ok) {
          throw new Error('HTTP error! status: ' + response.status);
        }

        var reader = response.body.getReader();
        var decoder = new TextDecoder();
        var buffer = '';

        function processStream() {
          reader.read().then(function (result) {
            if (result.done) {
              finalize();
              return;
            }

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
                  streamedContent.textContent = fullText;
                } else if (data.done) {
                  finalize();
                } else if (data.error) {
                  showError();
                  reader.cancel();
                  return;
                }
              } catch (e) {
                console.error('Error parsing SSE data:', e);
              }
            }

            processStream();
          }).catch(function (err) {
            console.error('Stream reading error:', err);
            showError();
            reader.cancel();
          });
        }

        processStream();
      })
      .catch(function (err) {
        console.error('Fetch error:', err);
        showError();
      });
  }
})();
