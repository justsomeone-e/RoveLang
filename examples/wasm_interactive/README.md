# Rove WebAssembly Interactive Calculator

An interactive, zero-dependency browser application powered by a WebAssembly computation core written in Rove (`calculator.rove`).

## What It Demonstrates

- **Direct Rove -> WebAssembly Compilation**: Fast mathematical and algorithmic routines compiled into a standalone `.wasm` binary.
- **ABI v1 ES Module Integration**: Clean JavaScript/TypeScript bindings (`bundle/calculator.mjs` and `bundle/calculator.d.ts`) generated automatically by `rove bundle`.
- **Browser Interop**: Asynchronous module initialization with `await initRoveModule()`, seamless calling of exported Rove functions from modern ES module scripts.

## Building the WASM Bundle

To rebuild the WebAssembly bundle:
```bash
rove bundle calculator.rove -o bundle --package
```

## Running the Web App

Start any local static HTTP server in this directory:
```bash
# Using Python
python -m http.server 8080

# Or using Node.js npx
npx serve .
```

Open `http://localhost:8080` in any modern web browser to interact with the Rove WebAssembly core in real-time.
