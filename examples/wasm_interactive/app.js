import {
    initRoveModule,
    add,
    subtract,
    multiply,
    divide,
    power,
    factorial,
    describe_calc
} from './bundle/calculator.mjs';

const statusEl = document.getElementById('status');
const resultEl = document.getElementById('result');
const historyEl = document.getElementById('history');
const inputA = document.getElementById('numA');
const inputB = document.getElementById('numB');

function log(msg) {
    const item = document.createElement('div');
    item.className = 'history-item';
    item.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
    historyEl.prepend(item);
}

async function boot() {
    try {
        await initRoveModule();
        const desc = describe_calc("WebWorker-0");
        statusEl.textContent = `Ready: ${desc}`;
        statusEl.style.color = '#38bdf8';
        log('WebAssembly runtime compiled and initialized.');
    } catch (err) {
        statusEl.textContent = `Failed to load WASM: ${err.message}`;
        statusEl.style.color = '#ef4444';
        console.error(err);
    }
}

function runOp(name, fn, isUnary = false) {
    const a = parseInt(inputA.value, 10) || 0;
    const b = parseInt(inputB.value, 10) || 0;
    let res = 0;
    if (isUnary) {
        res = fn(a);
        log(`${name}(${a}) => ${res}`);
    } else {
        res = fn(a, b);
        log(`${name}(${a}, ${b}) => ${res}`);
    }
    resultEl.textContent = res;
}

document.getElementById('btn-add').addEventListener('click', () => runOp('add', add));
document.getElementById('btn-sub').addEventListener('click', () => runOp('subtract', subtract));
document.getElementById('btn-mul').addEventListener('click', () => runOp('multiply', multiply));
document.getElementById('btn-div').addEventListener('click', () => runOp('divide', divide));
document.getElementById('btn-pow').addEventListener('click', () => runOp('power', power));
document.getElementById('btn-fac').addEventListener('click', () => runOp('factorial', factorial, true));

boot();
