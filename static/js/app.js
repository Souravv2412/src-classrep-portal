window.openModal = function openModal(id) {
  const node = document.getElementById(id);
  if (node) node.classList.add('active');
};

window.closeModal = function closeModal(id) {
  const node = document.getElementById(id);
  if (node) node.classList.remove('active');
};

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') {
    document.querySelectorAll('.modal-overlay.active').forEach((node) => node.classList.remove('active'));
  }
});

window.formatCampusBadge = function formatCampusBadge(campus) {
  const value = String(campus || '').toLowerCase();
  if (value.includes('south')) return '<span class="badge badge-green">South</span>';
  if (value.includes('downtown')) return '<span class="badge badge-blue">Downtown</span>';
  return `<span class="badge badge-gray">${campus || 'All'}</span>`;
};

window.shutdownPortal = function shutdownPortal() {
  const confirmed = window.confirm('Close SRC Portal now?');
  if (!confirmed) return;
  fetch('/shutdown', { method: 'POST' })
    .then(() => {
      window.close();
      window.location.href = 'about:blank';
    })
    .catch(() => {
      window.alert('Unable to close automatically. Use Stop SRC Portal.vbs.');
    });
};
