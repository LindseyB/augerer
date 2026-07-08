(function () {
  var drawButton = document.getElementById('drawButton');
  var lookupInput = document.getElementById('lookupInput');
  var lookupResults = document.getElementById('lookupResults');

  var errorText = document.getElementById('errorText');

  var currentResults = [];
  var activeIndex = -1;

  function setError(message) {
    if (!message) {
      errorText.hidden = true;
      errorText.textContent = '';
      return;
    }
    errorText.hidden = false;
    errorText.textContent = message;
  }

  function clearLookupResults() {
    lookupResults.innerHTML = '';
    lookupInput.setAttribute('aria-expanded', 'false');
    currentResults = [];
    activeIndex = -1;
  }

  function setActive(index) {
    var buttons = lookupResults.querySelectorAll('.lookup-btn');
    buttons.forEach(function (button, i) {
      button.classList.toggle('active', i === index);
    });
    activeIndex = index;
  }

  function openCardPage(slug, orientation) {
    var query = orientation ? ('?orientation=' + encodeURIComponent(orientation)) : '';
    window.location.href = '/card/' + encodeURIComponent(slug) + query;
  }

  function renderLookup(results) {
    clearLookupResults();
    if (!results.length) return;

    currentResults = results;
    lookupInput.setAttribute('aria-expanded', 'true');

    results.forEach(function (result, index) {
      var li = document.createElement('li');
      var button = document.createElement('button');
      button.type = 'button';
      button.className = 'lookup-btn';
      button.textContent = result.name;
      button.setAttribute('role', 'option');
      button.addEventListener('click', function () {
        lookupInput.value = result.name;
        clearLookupResults();
        openCardPage(result.slug, null);
      });
      button.addEventListener('mouseenter', function () {
        setActive(index);
      });
      li.appendChild(button);
      lookupResults.appendChild(li);
    });
  }

  function lookup(query) {
    if (!query.trim()) {
      clearLookupResults();
      return;
    }

    fetch('/api/lookup?q=' + encodeURIComponent(query.trim()))
      .then(function (response) { return response.json(); })
      .then(function (payload) {
        renderLookup(payload.results || []);
      })
      .catch(function () {
        setError('Lookup failed. Try again.');
      });
  }

  if (drawButton) {
    drawButton.addEventListener('click', function () {
      fetch('/api/draw')
        .then(function (response) { return response.json(); })
        .then(function (payload) {
          setError('');
          openCardPage(payload.card.slug, payload.orientation);
        })
        .catch(function () {
          setError('Draw failed. Please retry.');
        });
    });
  }

  lookupInput.addEventListener('input', function () {
    lookup(lookupInput.value);
  });

  lookupInput.addEventListener('keydown', function (event) {
    if (!currentResults.length) return;

    if (event.key === 'ArrowDown') {
      event.preventDefault();
      var next = activeIndex < currentResults.length - 1 ? activeIndex + 1 : 0;
      setActive(next);
      return;
    }

    if (event.key === 'ArrowUp') {
      event.preventDefault();
      var prev = activeIndex > 0 ? activeIndex - 1 : currentResults.length - 1;
      setActive(prev);
      return;
    }

    if (event.key === 'Enter') {
      event.preventDefault();
      if (activeIndex < 0) {
        activeIndex = 0;
      }
      var result = currentResults[activeIndex];
      lookupInput.value = result.name;
      clearLookupResults();
      openCardPage(result.slug, null);
      return;
    }

    if (event.key === 'Escape') {
      clearLookupResults();
    }
  });

  document.addEventListener('click', function (event) {
    if (event.target !== lookupInput && !lookupResults.contains(event.target)) {
      clearLookupResults();
    }
  });

  var actionTiles = Array.prototype.slice.call(document.querySelectorAll('.tile'));
  var reduceMotionQuery = window.matchMedia('(prefers-reduced-motion: reduce)');

  function allowTileGlowMotion() {
    return !reduceMotionQuery.matches;
  }

  function setTileGlowPosition(tile, clientX, clientY) {
    if (!allowTileGlowMotion()) return;
    var rect = tile.getBoundingClientRect();
    tile.style.setProperty('--edge-glow-x', clientX - rect.left + 'px');
    tile.style.setProperty('--edge-glow-y', clientY - rect.top + 'px');
  }

  actionTiles.forEach(function (tile) {
    tile.addEventListener('pointerenter', function (event) {
      if (!allowTileGlowMotion()) return;
      setTileGlowPosition(tile, event.clientX, event.clientY);
      tile.classList.add('glow-active');
    });

    tile.addEventListener('pointermove', function (event) {
      if (!allowTileGlowMotion()) return;
      setTileGlowPosition(tile, event.clientX, event.clientY);
    });

    tile.addEventListener('pointerleave', function () {
      tile.classList.remove('glow-active');
      tile.style.setProperty('--edge-glow-x', '92%');
      tile.style.setProperty('--edge-glow-y', '8%');
    });
  });
})();
