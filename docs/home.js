const byId = id => document.getElementById(id);
const form = byId('analysisForm');
const samples = byId('samples');
const budgetInput = byId('budget');
const example = samples.value;
let api;
let report;

function clearReport(message, state) {
  report = null;
  for (const id of ['average', 'minimum', 'maximum', 'overBudget']) byId(id).textContent = '—';
  byId('distribution').replaceChildren();
  byId('sampleCount').textContent = '— samples';
  byId('executionTime').textContent = 'Rove / WebAssembly';
  byId('downloadButton').disabled = true;
  byId('reportSummary').textContent = message;
  byId('resultState').textContent = state;
}

function analyze(event) {
  event?.preventDefault();
  if (!api) return;
  byId('inputError').textContent = '';
  samples.removeAttribute('aria-invalid');
  budgetInput.removeAttribute('aria-invalid');
  try {
    const raw = samples.value.trim();
    if (!raw || raw.length > 200000) throw new Error('Enter between 1 and 10,000 numeric samples (up to 200 KB of text).');
    // A comma must separate values; do not silently accept missing CSV cells.
    if (/(^|,)\s*(,|$)/.test(raw)) throw new Error('A comma-separated value is missing. Remove empty cells or supply a number.');
    const parts = raw.split(/[\s,]+/);
    if (parts.length > 10000) throw new Error('Use at most 10,000 samples per report.');
    const values = parts.map(part => {
      if (!/^(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(part)) throw new Error(`Invalid sample: ${part.slice(0, 24)}. Use nonnegative decimal numbers.`);
      const value = Number(part);
      if (!Number.isFinite(value) || value > 1000000) throw new Error('Each sample must be between 0 and 1,000,000 ms.');
      return value;
    });
    const budget = Number(budgetInput.value);
    if (!budgetInput.value.trim() || !Number.isFinite(budget) || budget < 0 || budget > 1000000) {
      budgetInput.setAttribute('aria-invalid', 'true');
      throw new Error('Set a budget between 0 and 1,000,000 ms.');
    }
    const start = performance.now();
    const count = api.sample_count(values);
    const over = api.count_over(values, budget);
    const ranges = [[0, 50], [50, 100], [100, 200], [200, 500], [500, 1000001]];
    report = {
      engine: 'Rove WASM / Bundle ABI v1', unit: 'ms', samples: count, budget,
      average: api.average(values), minimum: api.minimum(values), maximum: api.maximum(values),
      overBudget: over,
      distribution: ranges.map(([lower, upper]) => ({ lowerInclusive: lower, upperExclusive: upper, count: api.count_between(values, lower, upper) }))
    };
    const elapsed = performance.now() - start;
    for (const id of ['average', 'minimum', 'maximum']) byId(id).textContent = report[id].toLocaleString('en-US', { maximumFractionDigits: 2 });
    byId('overBudget').textContent = `${over} / ${count}`;
    byId('sampleCount').textContent = `${count.toLocaleString('en-US')} samples`;
    byId('reportSummary').textContent = over ? `${over} of ${count} requests exceeded your ${budget} ms budget.` : `All ${count} requests stayed within your ${budget} ms budget.`;
    byId('resultState').textContent = 'COMPUTED IN WASM';
    byId('executionTime').textContent = `${elapsed.toFixed(2)} ms · calls + ABI transfer`;
    const chart = byId('distribution');
    chart.replaceChildren();
    const labels = ['0–<50 ms', '50–<100 ms', '100–<200 ms', '200–<500 ms', '500+ ms'];
    report.distribution.forEach((bin, index) => {
      const row = document.createElement('div');
      row.className = 'bar-row';
      const label = document.createElement('span');
      label.textContent = labels[index];
      const track = document.createElement('span');
      track.className = 'bar-track';
      track.setAttribute('aria-hidden', 'true');
      const fill = document.createElement('span');
      fill.className = 'bar-fill';
      fill.style.width = `${bin.count / count * 100}%`;
      track.append(fill);
      const value = document.createElement('span');
      value.textContent = bin.count;
      row.append(label, track, value);
      chart.append(row);
    });
    byId('downloadButton').disabled = false;
  } catch (error) {
    if (!budgetInput.hasAttribute('aria-invalid')) samples.setAttribute('aria-invalid', 'true');
    byId('inputError').textContent = error.message;
    clearReport('Correct the input to generate a report.', 'INPUT REQUIRED');
  }
}

form.addEventListener('submit', analyze);
form.addEventListener('input', () => clearReport('Input changed. Analyze again to update the report.', 'INPUT CHANGED'));
byId('sampleButton').addEventListener('click', () => { samples.value = example; budgetInput.value = '200'; analyze(); });
byId('downloadButton').addEventListener('click', () => {
  if (!report) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2) + '\n'], { type: 'application/json' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = 'rove-latency-report.json';
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});

try {
  const { initRoveModule } = await import('./generated/metrics/metrics.mjs');
  api = await initRoveModule();
  byId('analyzeButton').disabled = false;
  byId('analyzeButton').textContent = 'Analyze samples →';
  byId('runtimeState').textContent = 'WASM ready · Data stays in this browser';
  analyze();
} catch {
  byId('analyzeButton').textContent = 'WASM unavailable';
  byId('runtimeState').textContent = 'Could not load WASM. Serve this directory over HTTP and reload, or use the CLI below.';
  clearReport('The compiled module could not load. No analysis was performed.', 'MODULE UNAVAILABLE');
} finally {
  byId('results').setAttribute('aria-busy', 'false');
}
