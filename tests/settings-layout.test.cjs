const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const app = fs.readFileSync(path.join(__dirname, '..', 'textfold', 'web', 'app.js'), 'utf8');
const start = app.indexOf('    function discoveryState() {');
const code = app.slice(start, app.indexOf('    function render() {', start));

function modelState({ refreshing = false, error = '' } = {}) {
  const context = vm.createContext({
    refreshing,
    refreshError: error,
    data: { discovery: {} },
    T: () => ({ st_models_h: 'Models', st_scanning: 'Scanning…', st_discovery_failed: 'Failed:', st_retry: 'Retry' }),
    esc: value => value,
  });
  vm.runInContext(`${code}\nthis.heading = modelHeading(); this.state = discoveryState();`, context);
  return context;
}

test('scanning sits in the section heading instead of adding a row that later disappears', () => {
  const scanning = modelState({ refreshing: true });
  assert.match(scanning.heading, /st-scan-state/);
  assert.match(scanning.heading, /Scanning…/);
  assert.equal(scanning.state, '');

  const stable = modelState();
  assert.doesNotMatch(stable.heading, /st-scan-state/);
  assert.equal(stable.state, '');
});

test('a discovery error still gets its own message and retry control', () => {
  const failed = modelState({ error: 'No service' });
  assert.match(failed.state, /Failed:/);
  assert.match(failed.state, /st-retry/);
  assert.doesNotMatch(failed.heading, /st-scan-state/);
});
