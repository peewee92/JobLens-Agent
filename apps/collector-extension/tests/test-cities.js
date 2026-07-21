const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

const context = { console };
context.globalThis = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync(require.resolve('../cities.js'), 'utf8'), context);
const data = context.BossCityData;

assert.strictEqual(data.defaultCity.name, '武汉');
assert.strictEqual(data.defaultCity.code, '101200100');
assert.strictEqual(data.nationwide.code, '100010000');
assert.strictEqual(data.provinces.length, 31);
assert.ok(data.cities.length >= 360);
assert.strictEqual(new Set(data.cities.map(city => city.code)).size, data.cities.length);
assert.strictEqual(new Set(data.cities.map(city => city.name)).size, data.cities.length);
assert.ok(data.cities.every(city => /^\d{9}$/.test(city.code)));
assert.strictEqual(data.byName['成都'].code, '101270100');
assert.strictEqual(data.byName['深圳'].code, '101280600');
assert.strictEqual(data.byName['襄阳'].code, '101200200');
assert.strictEqual(data.byName['苏州'].code, '101190400');
assert.ok(data.hotCities.some(city => city.name === '武汉'));

console.log(`City dataset tests passed: ${data.provinces.length} province-level groups, ${data.cities.length} cities.`);
