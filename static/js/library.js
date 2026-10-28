(function () {
  'use strict';

  var searchInput = document.getElementById('librarySearch');
  var filterBtns = document.querySelectorAll('.filter-btn');
  var cardItems = document.querySelectorAll('.card-grid-item');
  var currentFilter = 'all';
  var currentSearch = '';

  function applyFilters() {
    var query = currentSearch.toLowerCase().trim();
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
      filterBtns.forEach(function (b) { b.classList.remove('active'); });
      this.classList.add('active');
      currentFilter = this.dataset.filter || 'all';
      applyFilters();
    });
  });
}());
