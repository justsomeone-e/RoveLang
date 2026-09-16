# Nyx v5.0.3 — Daydream

Nyx v5.0.3 is a focused Daydream maintenance release. It fixes duplicate
execution in the browser preview, separates Studio state from Tour progress,
and ships a clearer emoji-free documentation and landing-page experience while
preserving the v5 language, Typed HIR v1, Bundle ABI v1, and backend maturity
contracts.

## Included

- Browser preview executes one explicit `main()` call exactly once.
- Worker/evaluator cache-busting ensures the published Studio receives fixes.
- Studio examples no longer overwrite Tour exercise state.
- Landing page and Studio hierarchy are clearer, with target/build status made
  explicit instead of implying browser compilation.
- Documentation and release-facing site surfaces contain no decorative emoji.

## Scope boundaries

C++20, JavaScript, and Python remain the stable backends. Rust, WebAssembly,
React, and ASM remain beta where documented. LLVM and C17 remain experimental;
this release does not claim full language or standard-library parity for them.
Capability selection is currently a target-feature contract with explicit
rejection. The planned resolver and `CapabilityPlan` remain documented roadmap
work, not shipped behavior.

## Install

### Windows PowerShell

    $env:NYX_RELEASE_TAG = 'v5.0.3'; irm https://raw.githubusercontent.com/justsomeone-e/nyx/v5.0.3/install.ps1 | iex

### Linux / macOS

    curl -fsSL https://raw.githubusercontent.com/justsomeone-e/nyx/v5.0.3/install.sh | NYX_RELEASE_TAG=v5.0.3 bash

## Verification

The targeted local browser, Node, HTML, JavaScript, emoji, and diff checks passed.
The tagged GitHub Actions workflow remains authoritative for the full regression
harness, Stage1 → Stage2 → Stage3 reproducibility, Python/Nyx canonical Typed
HIR parity, four-platform native binaries, VSIX, checksums, SBOM, and provenance.
