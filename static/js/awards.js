const awardSelect = document.getElementById('award-ref');
const awardName = document.getElementById('award-name');
const awardSearch = document.getElementById('award-search');

function syncAwardName() {
  if (!awardSelect || !awardName) return;
  awardName.value = awardSelect.options[awardSelect.selectedIndex]?.text.split('|')[0].trim() || '';
}

function filterAwardOptions() {
  if (!awardSelect || !awardSearch) return;
  const query = awardSearch.value.trim().toLowerCase();
  let firstVisibleIndex = -1;
  Array.from(awardSelect.options).forEach((option, index) => {
    const matches = !query || option.dataset.search.includes(query);
    option.hidden = !matches;
    if (matches && firstVisibleIndex === -1) firstVisibleIndex = index;
  });
  if (firstVisibleIndex >= 0) awardSelect.selectedIndex = firstVisibleIndex;
  syncAwardName();
}

awardSelect?.addEventListener('change', syncAwardName);
awardSearch?.addEventListener('input', filterAwardOptions);
syncAwardName();
filterAwardOptions();