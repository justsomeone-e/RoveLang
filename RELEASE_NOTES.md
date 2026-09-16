# Nyx v5.0.2 — Daydream

Nyx v5.0.2 is a checked compiler-foundations patch for the stable Daydream
line. It expands the MIR pipeline, module and generic validation, backend pilot
coverage, installer behavior, and the Tour while preserving the v5 language,
Typed HIR v1, Bundle ABI v1, and backend maturity contracts.

## Included

- Checked stable identities for source, modules, definitions, types, and
  generic instances.
- Per-module checking foundations with direct-import interfaces and linked HIR.
- MIR effects, coroutine, dispatch, aggregate, ABI, legalization, and backend
  pilot improvements with focused positive and negative tests.
- Experimental native `std/http` support with bounded direct process execution.
- Windows and Unix installer hardening, including extensionless Unix binaries
  and safer VS Code executable discovery.
- A project-driven Core Path for the Tour of Nyx and updated compiler docs.
- The M9-M24 Deep Compiler roadmap, including the future capability resolver:
  `requires`, `one_of`, `optional`, explicit preferences, and adapter contracts.

## Scope boundaries

C++20, JavaScript, and Python remain the stable backends. Rust, WebAssembly,
React, and ASM remain beta where documented. LLVM and C17 remain experimental;
this release does not claim full language or standard-library parity for them.
Capability selection is currently a target-feature contract with explicit
rejection. The planned resolver and `CapabilityPlan` are documented roadmap
work, not shipped behavior.

## Install

### Windows PowerShell

    $env:NYX_RELEASE_TAG = 'v5.0.2'; irm https://raw.githubusercontent.com/justsomeone-e/nyx/v5.0.2/install.ps1 | iex

### Linux / macOS

    curl -fsSL https://raw.githubusercontent.com/justsomeone-e/nyx/v5.0.2/install.sh | NYX_RELEASE_TAG=v5.0.2 bash

## Verification

The final local source revision passed the full regression harness with exit
code 0: `138/138` suites passed. The tagged GitHub Actions workflow remains
authoritative for Stage1 → Stage2 → Stage3 reproducibility, Python/Nyx
canonical Typed HIR parity, four-platform native binaries, VSIX, checksums,
SBOM, and provenance.
