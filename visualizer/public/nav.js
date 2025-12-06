(function () {
  if (document.querySelector('.nav-topbar')) return;

  const title = document.title || 'Dashboard';
  const bar = document.createElement('nav');
  bar.className = 'nav-topbar';
  bar.innerHTML = `
    <a class="nav-home" href="/" aria-label="Back to Dashboard">← Back to Dashboard</a>
    <span class="nav-spacer"></span>
    <span class="nav-title">${title}</span>
  `;

  const body = document.body;
  if (body.firstChild) {
    body.insertBefore(bar, body.firstChild);
  } else {
    body.appendChild(bar);
  }
})();

