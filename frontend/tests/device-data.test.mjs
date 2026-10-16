import {test} from 'node:test';
import assert from 'node:assert/strict';
import {normalizeDevices} from '../src/device-data.mjs';

test('mixed heartbeat app formats become readable labels without mutating API data', () => {
  const plugin = {id: 'mqtt', type: 'loxberry_plugin', name: 'MQTT', version: '1.2', folder: 'mqtt', author: 'Author', enabled: false, autoupdate: true};
  const devices = [{serial: 'QBX-TEST', metrics: {cpu_percent: 12}, apps: ['homeassistant', plugin, {name: 'nginx'}, {folder: 'legacy'}, {custom: 'record'}, null]}];
  const snapshot = structuredClone(devices);
  const result = normalizeDevices(devices);
  assert.deepEqual(result[0].apps, ['homeassistant', 'LoxBerry: MQTT 1.2 (disabled)', 'nginx', 'legacy', '{"custom":"record"}']);
  assert.deepEqual(devices, snapshot);
  assert.equal(result[0].serial, 'QBX-TEST');
  assert.deepEqual(result[0].metrics, {cpu_percent: 12});
});

test('absent and invalid app lists are safe to display', () => {
  for (const apps of [undefined, null, {}, 'nginx']) {
    assert.deepEqual(normalizeDevices([{serial: 'test', apps}])[0].apps, []);
  }
  assert.deepEqual(normalizeDevices([]), []);
});

test('malformed device responses are rejected for the UI to report', () => {
  for (const data of [{detail: 'upstream error'}, null, [null], [[]]]) {
    assert.throws(() => normalizeDevices(data), /Ongeldige/);
  }
});
