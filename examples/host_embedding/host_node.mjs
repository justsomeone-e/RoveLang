// Node.js Host for Rove WebAssembly Bundle
import { initRoveModule, sum_floats, mutate_add_in_place, format_summary } from './bundle/transformer.mjs';
import assert from 'node:assert/strict';

console.log('[*] Initializing Rove WASM module in Node.js...');
await initRoveModule();

// 1. Float vector sum across WASM boundary
const floatInput = new Float64Array([10.5, 20.25, 30.25, 40.0]);
const sumResult = sum_floats(floatInput);
console.log(`[+] sum_floats: result = ${sumResult} (expected: 101.0)`);
assert.equal(sumResult, 101.0);

// 2. In-place integer array mutation across WASM linear memory
const intBuffer = new Int32Array([10, 20, 30, 40]);
const count = mutate_add_in_place(intBuffer, 5);
console.log(`[+] mutate_add_in_place: count = ${count}, buffer = [${Array.from(intBuffer).join(', ')}]`);
assert.equal(count, 4);
assert.deepEqual(Array.from(intBuffer), [15, 25, 35, 45]);

// 3. String formatting across WASM UTF-8 boundary
const summary = format_summary('SensorTelemetry');
console.log(`[+] format_summary: "${summary}"`);
assert.equal(summary, 'Summary: SensorTelemetry [OK]');

console.log('\n[SUCCESS] Node.js host embedding verified successfully!');
