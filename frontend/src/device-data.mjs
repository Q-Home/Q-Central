// Stored heartbeats can contain both app names and structured plugin records.
// Convert both API sources before their data reaches React components.
function text(value) {
  return typeof value === 'string' || typeof value === 'number' ? String(value) : '';
}

export function appLabel(app) {
  if (app == null) return '';
  if (typeof app !== 'object') return text(app);
  const name = text(app.name) || text(app.folder) || text(app.id);
  if (app.type === 'loxberry_plugin' && name) {
    const version = text(app.version);
    return `LoxBerry: ${name}${version ? ` ${version}` : ''}${app.enabled === false ? ' (disabled)' : ''}`;
  }
  return name || JSON.stringify(app);
}

export function normalizeDevices(devices) {
  if (!Array.isArray(devices)) throw new Error('Ongeldige devicelijst ontvangen.');
  return devices.map(device => {
    if (!device || typeof device !== 'object' || Array.isArray(device)) {
      throw new Error('Ongeldige devicegegevens ontvangen.');
    }
    return {
      ...device,
      apps: Array.isArray(device.apps) ? device.apps.map(appLabel).filter(Boolean) : [],
    };
  });
}
