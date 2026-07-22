(function () {
  'use strict';

  var container = document.createElement('div');
  container.id = 'starfield';
  container.setAttribute('aria-hidden', 'true');
  document.body.insertBefore(container, document.body.firstChild);

  function seeded(seed) {
    var s = seed;
    return function () {
      s = (s * 1664525 + 1013904223) & 0xffffffff;
      return (s >>> 0) / 4294967295;
    };
  }

  var rand = seeded(42);

  function makeStar(cls, size, left, top, opacity, animDur, animDelay) {
    var el = document.createElement('span');
    el.className = 'star' + (cls ? ' ' + cls : '');
    var css = 'left:' + left + '%;top:' + top + '%;width:' + size + 'px;height:' + size + 'px;opacity:' + opacity + ';';
    if (animDur) {
      css += 'animation:twinkle ' + animDur + 's ' + animDelay + 's ease-in-out infinite;';
    }
    el.style.cssText = css;
    container.appendChild(el);
  }

  var i;

  // Layer 1: dust particles — many, tiny, still
  for (i = 0; i < 180; i++) {
    makeStar('', rand() * 1.2 + 0.4, rand() * 100, rand() * 100, rand() * 0.28 + 0.04, 0, 0);
  }

  // Layer 2: medium stars with twinkle
  for (i = 0; i < 60; i++) {
    makeStar('', rand() * 1.5 + 1.2, rand() * 100, rand() * 100, rand() * 0.45 + 0.2,
      (rand() * 4 + 2).toFixed(1), (rand() * 6).toFixed(1));
  }

  // Layer 3: bright gold accent stars
  for (i = 0; i < 18; i++) {
    makeStar('star-gold', rand() * 2 + 1.8, rand() * 100, rand() * 100, rand() * 0.5 + 0.35,
      (rand() * 4 + 4).toFixed(1), (rand() * 8).toFixed(1));
  }
}());
