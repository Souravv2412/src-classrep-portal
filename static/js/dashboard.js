const palette = ['#006838', '#d6a329', '#1d4ed8', '#0f8f50', '#7a5c00', '#8b5cf6'];
const chartRefs = {};

function buildChart(id, type, labels, data) {
  const ctx = document.getElementById(id);
  if (!ctx) return;
  if (chartRefs[id]) chartRefs[id].destroy();
  chartRefs[id] = new Chart(ctx, {
    type,
    data: {
      labels,
      datasets: [{
        data,
        backgroundColor: palette,
        borderRadius: type === 'bar' ? 10 : 0,
      }],
    },
    options: {
      responsive: true,
      plugins: { legend: { position: 'bottom' } },
      scales: type === 'bar' ? { y: { beginAtZero: true, ticks: { precision: 0 } } } : {},
    },
  });
}

function updateKpis(data) {
  const root = document.getElementById('dashboard-kpis');
  root.innerHTML = `
    <div class="kpi"><div class="kpi-label">Total applications</div><div class="kpi-value">${data.total}</div><div class="kpi-sub">Filtered class rep records</div></div>
    <div class="kpi"><div class="kpi-label">South campus</div><div class="kpi-value">${data.south}</div><div class="kpi-sub">South Windsor records</div></div>
    <div class="kpi"><div class="kpi-label">Downtown campus</div><div class="kpi-value">${data.downtown}</div><div class="kpi-sub">Downtown Windsor records</div></div>
    <div class="kpi"><div class="kpi-label">Current ranking</div><div class="kpi-value">${data.ranked_reps}</div><div class="kpi-sub">Reps scored this semester</div></div>
  `;
}

function refreshDashboard() {
  const params = new URLSearchParams({
    campus: document.getElementById('dash-campus').value,
    intake: document.getElementById('dash-intake').value,
    year: document.getElementById('dash-year').value,
    month: document.getElementById('dash-month').value,
  });

  fetch(`/api/stats?${params.toString()}`)
    .then((response) => response.json())
    .then((data) => {
      updateKpis(data.kpis);
      buildChart('campusChart', 'doughnut', Object.keys(data.campuses), Object.values(data.campuses));
      buildChart('intakeChart', 'doughnut', Object.keys(data.intakes), Object.values(data.intakes));
      buildChart('yearChart', 'bar', Object.keys(data.by_year), Object.values(data.by_year));
      buildChart('programChart', 'bar', Object.keys(data.programs), Object.values(data.programs));
    });
}

document.getElementById('dash-campus')?.addEventListener('change', refreshDashboard);
document.getElementById('dash-intake')?.addEventListener('change', refreshDashboard);
document.getElementById('dash-year')?.addEventListener('change', refreshDashboard);
document.getElementById('dash-month')?.addEventListener('change', refreshDashboard);
document.getElementById('dash-clear')?.addEventListener('click', () => {
  ['dash-campus', 'dash-intake', 'dash-year', 'dash-month'].forEach((id) => { document.getElementById(id).value = ''; });
  refreshDashboard();
});
refreshDashboard();
