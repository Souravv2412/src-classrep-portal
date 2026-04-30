const engagementSearch = document.getElementById('engagement-search');
const engagementSelect = document.getElementById('engagement-ref');

function filterEngagementOptions() {
  if (!engagementSearch || !engagementSelect) return;
  const query = engagementSearch.value.trim().toLowerCase();
  let firstVisibleIndex = -1;
  Array.from(engagementSelect.options).forEach((option, index) => {
    const matches = !query || option.dataset.search.includes(query);
    option.hidden = !matches;
    if (matches && firstVisibleIndex === -1) firstVisibleIndex = index;
  });
  if (firstVisibleIndex >= 0) engagementSelect.selectedIndex = firstVisibleIndex;
}

engagementSearch?.addEventListener('input', filterEngagementOptions);
filterEngagementOptions();