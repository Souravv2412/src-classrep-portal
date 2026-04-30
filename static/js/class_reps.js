const checkAll = document.getElementById('check-all');
checkAll?.addEventListener('change', () => {
  document.querySelectorAll('.rep-checkbox').forEach((box) => { box.checked = checkAll.checked; });
});

document.getElementById('email-selected')?.addEventListener('click', () => {
  const selected = Array.from(document.querySelectorAll('.rep-checkbox:checked')).map((node) => node.value);
  if (!selected.length) {
    window.alert('Please select at least one class rep.');
    return;
  }
  window.location.href = `/emails?selected_refs=${selected.join(',')}`;
});
