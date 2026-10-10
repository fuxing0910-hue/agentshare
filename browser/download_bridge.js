/* Narrow opaque-iframe -> parent download protocol; no network or storage. */
(function(root) {
  'use strict';
  const files = new Map([
    ['agentshare-selected.md','text/markdown;charset=utf-8'],
    ['agentshare-selected.html','text/html;charset=utf-8'],
  ]);
  function validateRequest(event, expectedSource, token) {
    if (!expectedSource || event.source !== expectedSource || event.origin !== 'null' || typeof token !== 'string' || token.length !== 32) return null;
    const value = event.data;
    if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
    if (value.type !== 'agentshare-download' || value.token !== token) return null;
    if (Object.keys(value).sort().join(',') !== 'content,filename,mime,selected_count,token,type') return null;
    if (!files.has(value.filename) || files.get(value.filename) !== value.mime) return null;
    if (typeof value.content !== 'string' || !value.content.length || value.content.length > 120 * 1024 * 1024) return null;
    if (!Number.isInteger(value.selected_count) || value.selected_count < 1 || value.selected_count > 5000) return null;
    return {content:value.content, filename:value.filename, mime:value.mime, selected_count:value.selected_count};
  }
  function portableTool(assets) {
    const payload = JSON.stringify(assets).replace(/[&<>\u2028\u2029]/gu, character => ({'&':'\\u0026','<':'\\u003c','>':'\\u003e','\u2028':'\\u2028','\u2029':'\\u2029'}[character]));
    // Rebuild immutable source constants; never serialize the live review DOM.
    const codeMarker = '__DOWNLOAD_' + 'BRIDGE_JS__', dataMarker = '__BROWSER_' + 'ASSETS_JSON__';
    return assets.shell.replace(codeMarker, () => assets.bridge).replace(dataMarker, () => payload);
  }
  const api = Object.freeze({validateRequest,portableTool});
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.AgentShareDownloadBridge = api;
})(globalThis);
