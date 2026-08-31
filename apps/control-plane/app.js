const runButton = document.querySelector('#runBtn');
const replayButton = document.querySelector('#replayBtn');

function setUnavailable(button, label) {
  if (!button) return;
  const original = button.textContent;
  button.textContent = label;
  button.disabled = true;
  window.setTimeout(() => {
    button.textContent = original;
    button.disabled = false;
  }, 1400);
}

// UI actions never simulate execution or verification. Until real API endpoints are
// connected, they explicitly report the missing authoritative backend operation.
runButton?.addEventListener('click', () => setUnavailable(runButton, 'Kernel API required'));
replayButton?.addEventListener('click', () => setUnavailable(replayButton, 'Replay API required'));

document.querySelectorAll('nav a').forEach(link => {
  link.addEventListener('click', () => {
    document.querySelectorAll('nav a').forEach(a => a.classList.remove('active'));
    link.classList.add('active');
  });
});
