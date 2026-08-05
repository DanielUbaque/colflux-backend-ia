(function () {
  const page    = location.pathname.split('/').pop() || 'index.html';
  const inPages = location.pathname.includes('/pages/');
  const base    = inPages ? '' : 'pages/';
  const root    = inPages ? '../' : '';

  const NAV_LINKS = [
    { href: `${base}team.html`,                   label: 'Equipo',           id: 'team.html' },
    { href: `${base}db.html`,                     label: 'Base de datos',    id: 'db.html' },
    { href: `${base}data.html`,                   label: '📂 Datos',         id: 'data.html' },
  ];

  function navHTML() {
    const links = NAV_LINKS.map(({ href, label, id }) => {
      const active = id === page ? ' class="active"' : '';
      return `<li><a href="${href}"${active}>${label}</a></li>`;
    }).join('\n      ');

    return `<nav>
  <div class="nav-inner">
    <a class="nav-logo" href="${root}index.html">🌿 COLFLUX · OE2</a>
    <ul class="nav-links">
      ${links}
    </ul>
    <span id="role-guard-selector"></span>
    <a class="nav-pill" href="https://github.com/colflux/backend" target="_blank">GitHub →</a>
  </div>
</nav>`;
  }

  function footerHTML() {
    return `<footer>
  <div class="container">
    <div class="footer-inner">
      <span>🌿 COLFLUX OE2 — Sistema de gestión de datos</span>
      <div class="footer-links">
        <a href="https://github.com/colflux/backend" target="_blank">GitHub</a>
        <a href="${base}db.html">Base de datos</a>
      </div>
    </div>
  </div>
</footer>`;
  }

  const navEl    = document.getElementById('app-nav');
  const footerEl = document.getElementById('app-footer');
  if (navEl)    navEl.outerHTML    = navHTML();
  if (footerEl) footerEl.outerHTML = footerHTML();
})();
