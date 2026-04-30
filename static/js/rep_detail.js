document.querySelectorAll('.attendance-edit').forEach((button) => {
  button.addEventListener('click', () => {
    document.getElementById('attendance-meeting-id').value = button.dataset.meetingId;
    document.getElementById('attendance-title').value = button.dataset.title;
    document.getElementById('attendance-status').value = button.dataset.status;
    document.getElementById('attendance-note').value = button.dataset.note;
    openModal('attendance-modal');
  });
});

document.getElementById('save-attendance')?.addEventListener('click', () => {
  fetch('/update-attendance', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ref: window.REP_REF,
      meeting_id: document.getElementById('attendance-meeting-id').value,
      status: document.getElementById('attendance-status').value,
      note: document.getElementById('attendance-note').value,
    }),
  }).then(() => window.location.reload());
});

document.getElementById('save-relay')?.addEventListener('click', () => {
  fetch('/update-relay', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ref: window.REP_REF, proof: document.getElementById('relay-proof').value }),
  }).then(() => window.location.reload());
});

document.getElementById('save-notes')?.addEventListener('click', () => {
  fetch('/api/save-notes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ref: window.REP_REF, notes: document.getElementById('vp-notes').value }),
  }).then(() => window.alert('Notes saved.'));
});
