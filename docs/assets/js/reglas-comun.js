// Helpers compartidos por las páginas de reglas de autollenado / validación:
// regla-detalle.html, regla-validacion.html, reglas-campo.html.
(function (global) {
  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // Lee de la URL los parámetros que todas estas páginas comparten
  // (fuente/carga, para poder volver a la carga de origen).
  function leerFuenteCarga() {
    const params = new URLSearchParams(window.location.search);
    return { fuenteId: params.get('fuente'), cargaId: params.get('carga') };
  }

  // Arma un querystring agregando fuente/carga si están presentes, para no
  // perder ese contexto al navegar entre páginas de reglas.
  function conFuenteCarga(base, fuenteId, cargaId) {
    const qs = new URLSearchParams(base);
    if (fuenteId) qs.set('fuente', fuenteId);
    if (cargaId) qs.set('carga', cargaId);
    return qs;
  }

  async function fetchJson(url, opciones) {
    const res = await fetch(url, opciones);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    return data;
  }

  function cargarDetalleRegla(apiBase, codigo) {
    return fetchJson(`${apiBase}/api/reglas-autollenado/${encodeURIComponent(codigo)}/`);
  }

  function listarReglas(apiBase) {
    return fetchJson(`${apiBase}/api/reglas-autollenado/`);
  }

  global.ReglasComun = {
    escapeHtml, leerFuenteCarga, conFuenteCarga, fetchJson, cargarDetalleRegla, listarReglas,
  };
})(window);
