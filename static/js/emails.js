const BATCH_SIZE = 80;

function visibleRecipientNodes() {
  return Array.from(document.querySelectorAll('.recipient-item')).filter((item) => item.style.display !== 'none');
}

function getSelectedRecipientNodes() {
  return Array.from(document.querySelectorAll('.email-recipient:checked'));
}

function updateSelectedCount() {
  const count = getSelectedRecipientNodes().length;
  const allVisible = visibleRecipientNodes().length;
  const node = document.getElementById('selected-count');
  const selectAll = document.getElementById('select-all-recipients');
  if (node) node.textContent = `${count} selected`;
  if (selectAll) selectAll.checked = allVisible > 0 && count === allVisible;
}

function applyRecipientSearch() {
  const query = (document.getElementById('recipient-search')?.value || '').trim().toLowerCase();
  document.querySelectorAll('.recipient-item').forEach((item) => {
    const match = !query || (item.dataset.search || '').includes(query);
    item.style.display = match ? '' : 'none';
    if (!match) {
      const checkbox = item.querySelector('.email-recipient');
      if (checkbox) checkbox.checked = false;
    }
  });
  updateSelectedCount();
}

function selectedRecipients() {
  return getSelectedRecipientNodes().map((node) => ({
    name: node.dataset.name || 'Recipient',
    email: node.dataset.email || '',
  })).filter((item) => item.email);
}

function chunk(array, size) {
  const parts = [];
  for (let i = 0; i < array.length; i += size) {
    parts.push(array.slice(i, i + size));
  }
  return parts;
}

function openSendUrl(kind) {
  const recipients = selectedRecipients();
  const subject = (document.getElementById('email-subject')?.value || '').trim();
  const body = (document.getElementById('email-body')?.value || '').trim();

  if (!recipients.length) {
    window.alert('Please select at least one recipient.');
    return;
  }
  if (!subject || !body) {
    window.alert('Please enter subject and message first.');
    return;
  }

  const recipientBatches = chunk(recipients.map((item) => item.email), BATCH_SIZE);
  if (recipientBatches.length > 1) {
    const ok = window.confirm(`Large send detected (${recipients.length} recipients). This will open ${recipientBatches.length} compose windows in batches of ${BATCH_SIZE} BCC recipients to reduce account risk. Continue?`);
    if (!ok) return;
  }

  const qSubject = encodeURIComponent(subject);
  const qBody = encodeURIComponent(body);
  recipientBatches.forEach((batchEmails, index) => {
    const qBcc = encodeURIComponent(batchEmails.join(','));
    let url = `mailto:?bcc=${qBcc}&subject=${qSubject}&body=${qBody}`;
    if (kind === 'gmail') {
      url = `https://mail.google.com/mail/?view=cm&fs=1&to=&bcc=${qBcc}&su=${qSubject}&body=${qBody}`;
    } else if (kind === 'outlook') {
      url = `https://outlook.office.com/mail/deeplink/compose?to=&bcc=${qBcc}&subject=${qSubject}&body=${qBody}`;
    }
    setTimeout(() => window.open(url, '_blank'), index * 350);
  });
}

document.querySelectorAll('.email-recipient').forEach((node) => node.addEventListener('change', updateSelectedCount));
document.getElementById('select-all-recipients')?.addEventListener('change', (event) => {
  const shouldSelect = event.target.checked;
  visibleRecipientNodes().forEach((item) => {
    const checkbox = item.querySelector('.email-recipient');
    if (checkbox) checkbox.checked = shouldSelect;
  });
  updateSelectedCount();
});
document.getElementById('recipient-search')?.addEventListener('input', applyRecipientSearch);

document.querySelectorAll('.template-btn').forEach((button) => {
  button.addEventListener('click', () => {
    document.getElementById('email-subject').value = button.dataset.subject;
    document.getElementById('email-body').value = decodeURIComponent(button.dataset.body);
  });
});

['email-campus', 'email-intake', 'email-year'].forEach((id) => {
  document.getElementById(id)?.addEventListener('change', () => {
    const params = new URLSearchParams({
      campus: document.getElementById('email-campus').value,
      intake: document.getElementById('email-intake').value,
      year: document.getElementById('email-year').value,
    });
    window.location.href = `/emails?${params.toString()}`;
  });
});

document.getElementById('open-send-options')?.addEventListener('click', () => {
  const recipients = selectedRecipients();
  const subject = (document.getElementById('email-subject')?.value || '').trim();
  const body = (document.getElementById('email-body')?.value || '').trim();

  if (!recipients.length) {
    window.alert('Please select at least one recipient.');
    return;
  }
  if (!subject || !body) {
    window.alert('Please enter subject and message first.');
    return;
  }

  const listNode = document.getElementById('send-recipient-list');
  const summaryNode = document.getElementById('send-summary');
  const subjectNode = document.getElementById('send-preview-subject');
  const bodyNode = document.getElementById('send-preview-body');

  if (listNode) {
    listNode.innerHTML = recipients.map((r) => `${r.name} (${r.email})`).join('<br>');
  }
  if (summaryNode) {
    summaryNode.textContent = `${recipients.length} recipient(s) selected.`;
  }
  if (subjectNode) subjectNode.textContent = `Subject: ${subject}`;
  if (bodyNode) bodyNode.textContent = body;

  openModal('send-options-modal');
});

document.getElementById('send-default-mail')?.addEventListener('click', () => openSendUrl('default'));
document.getElementById('send-gmail')?.addEventListener('click', () => openSendUrl('gmail'));
document.getElementById('send-outlook')?.addEventListener('click', () => openSendUrl('outlook'));

applyRecipientSearch();
updateSelectedCount();
