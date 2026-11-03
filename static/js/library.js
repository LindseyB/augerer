(function () {
  'use strict';

  var searchInput = document.getElementById('librarySearch');
  var filterBtns = document.querySelectorAll('.filter-btn');
  var cardItems = document.querySelectorAll('.card-grid-item');
  var currentFilter = 'all';
  var currentSearch = '';

  var NUMBER_WORDS = {
    '1': 'ace', '2': 'two', '3': 'three', '4': 'four', '5': 'five',
    '6': 'six', '7': 'seven', '8': 'eight', '9': 'nine', '10': 'ten',
    '11': 'page', '12': 'knight', '13': 'queen', '14': 'king'
  };

  function normalizeQuery(query) {
    return query.replace(/\b\d+\b/g, function (digits) {
      return NUMBER_WORDS[String(Number(digits))] || digits;
    });
  }

  function applyFilters() {
    var query = normalizeQuery(currentSearch.toLowerCase().trim());
    cardItems.forEach(function (item) {
      var arcana = item.dataset.arcana || '';
      var name = (item.dataset.name || '').toLowerCase();

      var filterMatch =
        currentFilter === 'all' ||
        (currentFilter === 'major' && arcana === 'major') ||
        (currentFilter === 'minor' && arcana !== 'major');

      var searchMatch = !query || name.includes(query);

      item.style.display = filterMatch && searchMatch ? '' : 'none';
    });
  }

  if (searchInput) {
    searchInput.addEventListener('input', function () {
      currentSearch = this.value;
      applyFilters();
    });
  }

  filterBtns.forEach(function (btn) {
    btn.addEventListener('click', function () {
      filterBtns.forEach(function (b) {
        b.classList.remove('active');
        b.setAttribute('aria-pressed', 'false');
      });
      this.classList.add('active');
      this.setAttribute('aria-pressed', 'true');
      currentFilter = this.dataset.filter || 'all';
      applyFilters();
    });
  });
}());
