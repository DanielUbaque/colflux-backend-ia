(function configureProyectosSection(window) {
  window.COLFLUX_DATA = window.COLFLUX_DATA || {};

  function get(id) {
    return document.getElementById(id);
  }

  function renderProjectFilter() {
    const { state } = window.COLFLUX_DATA.dataPage;
    const select = get('projectFilter');
    const current = select.value;
    select.innerHTML = '<option value="">Todos los proyectos</option>';

    for (const p of state.data.proyectos) {
      const option = document.createElement('option');
      option.value = p.id;
      option.textContent = p.nombre;
      select.appendChild(option);
    }

    const sinProyecto = document.createElement('option');
    sinProyecto.value = 'sin-proyecto';
    sinProyecto.textContent = 'Fuentes sin proyecto';
    select.appendChild(sinProyecto);

    select.value = current;
  }

  function renderTable() {
    const { state, escapeHtml, filteredProyectos } = window.COLFLUX_DATA.dataPage;
    const body = get('proyectosTableBody');
    const items = filteredProyectos();
    get('projectsCount').textContent = `${items.length} proyecto${items.length !== 1 ? 's' : ''}`;
    get('projectsPager').textContent = 'Página 1 de 1';

    if (items.length === 0) {
      body.innerHTML = '<tr><td colspan="4"><div class="state-box">No hay proyectos para mostrar.</div></td></tr>';
      return;
    }

    body.innerHTML = items.map(p => {
      const fuentes = state.data.fuentes.filter(f => Number(f.proyecto?.id) === Number(p.id));
      const completas = fuentes.filter(f => f.estado === 'completo').length;
      const pendientes = fuentes.filter(f => f.estado === 'pendiente').length;
      const errores = fuentes.filter(f => f.estado === 'con_errores').length;

      return `
        <tr>
          <td>
            <div class="source-title">${escapeHtml(p.nombre)}</div>
          </td>
          <td><strong>${fuentes.length}</strong> fuente${fuentes.length !== 1 ? 's' : ''}</td>
          <td>
            <span class="source-muted">${completas} completas · ${pendientes} pendientes · ${errores} con errores</span>
          </td>
          <td>
            <div class="source-actions">
              <button class="btn-table-action wide" onclick="filterByProject(${Number(p.id)})">Ver fuentes</button>
              <a class="btn-table-action wide" href="etl-datos.html?proyecto=${Number(p.id)}">📊 Ver datos cargados</a>
            </div>
          </td>
        </tr>`;
    }).join('');
  }

  function filterByProject(id) {
    get('projectFilter').value = String(id);
    get('fuentesTableSection').scrollIntoView({ behavior: 'smooth', block: 'start' });
    window.COLFLUX_DATA.dataPage.render();
  }

  function render() {
    renderProjectFilter();
    renderTable();
  }

  window.COLFLUX_DATA.proyectosSection = { render, filterByProject };
  window.filterByProject = filterByProject;
})(window);
