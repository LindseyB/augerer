/**
 * Tints the tarot card SVGs to match the current theme + the card's border
 * accent. Shared by the reading and card-detail pages.
 *
 * Any element with [data-card-image="true"] is re-fetched with mode/flat/color
 * query params whenever the <html> theme class changes.
 */
(function () {
  'use strict';

  var images = document.querySelectorAll('[data-card-image="true"]');
  if (!images.length) return;

  var probe = document.createElement('canvas');
  probe.width = 1;
  probe.height = 1;
  var probeCtx = probe.getContext('2d', { willReadFrequently: true });

  function toHex(component) {
    var n = Math.max(0, Math.min(255, Math.round(Number(component)))).toString(16);
    return n.length === 1 ? '0' + n : n;
  }

  // Resolve ANY CSS color string (rgb, oklch, color-mix, oklab, ...) to a
  // concrete #rrggbb by painting it and reading back the sRGB pixel. This
  // avoids fragile string parsing of color spaces the browser may report.
  function resolveHex(cssColor) {
    if (!cssColor || !probeCtx) return null;
    probeCtx.clearRect(0, 0, 1, 1);
    probeCtx.fillStyle = '#000000';
    probeCtx.fillStyle = cssColor;
    probeCtx.fillRect(0, 0, 1, 1);
    var data = probeCtx.getImageData(0, 0, 1, 1).data;
    return '#' + toHex(data[0]) + toHex(data[1]) + toHex(data[2]);
  }

  function applyTint(image) {
    var baseSrc = image.getAttribute('data-base-src') || image.getAttribute('src');
    if (!baseSrc) return;
    image.style.filter = 'none';
    var isDark = document.documentElement.classList.contains('dark');
    var next = new URL(baseSrc, window.location.origin);
    next.searchParams.set('mode', isDark ? 'dark' : 'light');
    next.searchParams.set('flat', '1');
    var hex = resolveHex(window.getComputedStyle(image).borderTopColor);
    if (hex) next.searchParams.set('color', hex);
    if (image.getAttribute('src') !== next.toString()) {
      image.setAttribute('src', next.toString());
    }
  }

  function applyAll() {
    images.forEach(applyTint);
  }

  applyAll();

  var observer = new MutationObserver(applyAll);
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ['class'],
  });
})();
