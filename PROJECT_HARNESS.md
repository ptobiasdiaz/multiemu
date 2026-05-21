# Project Harness

This document defines the engineering rules for `multiemu`.

Its purpose is to keep the project coherent while it grows:

- machine implementations should look and behave consistently
- performance-sensitive code should not regress during refactors
- accelerated Cython code should remain testable against Python references
- save/load state and debug support should remain first-class

These rules are intended to be practical. If a change conflicts with them, the burden is on the change to justify itself clearly.

## 1. Repository Responsibilities

### `machines/`

Machine modules are responsible for wiring:

- memory map
- port map / bus hookup
- ROM/media slots
- frame stepping orchestration
- state serialization
- debug device exposure

Machine modules should not absorb reusable chip logic that belongs elsewhere.

### `chipsets/`

`chipsets/` contains reusable emulated hardware blocks:

- audio chips
- video chips
- IO chips
- reusable timing-sensitive silicon behavior

If a block is reusable across machines and materially represents a chip, it belongs here.

### `devices/`

`devices/` contains non-chip mapped helpers and media/peripheral logic:

- tape/disk/cartridge helpers
- mapped memory helpers
- machine-adjacent peripherals that are not best modeled as chips

Examples:

- `OpenBus`
- `ByteRAM`
- `NibbleRAM`

are `devices`, not CPU internals and not machine-specific hacks.

### `cpu/`

`cpu/` contains CPU cores and CPU-adjacent generic bus/memory logic.

It must not accumulate machine-specific behavior unless that behavior is truly part of the processor core or its generic bus contract.

### `tests/fallbacks/`

Python reference implementations used as correctness or equivalence oracles belong here.

They are test assets, not production fallbacks.

## 2. Python First, Cython Second

New machine or chip work should follow this order:

1. Implement the behavior in Python first.
2. Add tests against the Python implementation.
3. Validate behavior with real software where possible.
4. Only then port hot paths to Cython.
5. Keep the Python reference in tests when it is useful as an equivalence oracle.

This rule exists to preserve debuggability and testability.

## 3. No Production Fallbacks For Cythonized Chips

If a chip has a production Cython implementation, production should use that implementation directly.

Do not keep Python runtime fallback classes for such chips in the normal import path unless there is a strong operational reason.

Python references for accelerated chips should live under `tests/fallbacks/`.

This avoids:

- silent divergence between Python and Cython production paths
- accidental imports of stale modules
- architecture drift where test references leak into runtime

## 4. Performance Rules

Performance-sensitive code must be treated differently from cold-path code.

### Safe refactor targets

These are usually safe to reorganize without performance risk:

- registry wiring
- machine factories
- ROM/path resolution
- state blob validation
- debug device assembly
- CLI plumbing
- test organization
- documentation

### Hot paths

These require more discipline:

- CPU stepping
- `run_until()` loops
- per-frame stepping
- scanline renderers
- sprite/tile raster code
- audio sample generation
- per-access mapper/bus logic

Refactors that touch hot paths must not be accepted blindly.

The process is:

1. measure baseline behavior or speed
2. make the change
3. measure again
4. reject the refactor if the regression is meaningful and unjustified

Structural cleanup is not a sufficient reason to slow down emulation.

## 5. State And Debug Are First-Class

Published machine support should preserve:

- `read_state()`
- `write_state()`
- snapshot usability where applicable
- `debug_devices()`

State support is not optional polish. It is part of the project contract.

If a new chip or machine becomes significant enough to ship, it should integrate cleanly with:

- runtime save/restore
- debug inspection
- deterministic test scenarios where possible

## 6. Naming Rules

Use canonical hardware names where practical.

Examples:

- use chip names such as `TMS9918A`
- prefer domain-correct names like `Sega8VDP` over legacy or misleading machine-local names

Avoid names that hide responsibility:

- do not call generic mapped memory blocks `mappers`
- do not keep obsolete compatibility names as the public API unless there is a real compatibility need

Compatibility aliases may exist locally, but canonical names should dominate source, tests, and exports.

## 7. Generated Artifacts

Generated artifacts must not be mistaken for source.

The repository should be routinely cleanable of:

- `__pycache__/`
- `build/`
- `.pytest_cache/`
- `.tox/`
- `*.egg-info/`
- `*.pyc`
- `*.so`
- generated Cython `*.c`
- coverage outputs

Use:

```bash
tox -e clean
```

to remove generated artifacts from the project tree without touching `.git` or `.venv`.

After cleaning, rebuild explicitly:

```bash
.venv/bin/python setup.py build_ext --inplace
```

or:

```bash
.venv/bin/pip install ./
```

## 8. Validation Discipline

Tests are necessary but not sufficient.

When changing emulation code, prefer a combination of:

- unit tests
- equivalence tests against Python references
- state/debug roundtrip tests
- real software smoke tests using ROMs, disks, tapes, or snapshots

Coverage gaps do not automatically prove dead code. Coverage should be read together with:

- static references/import usage
- runtime entry points
- machine registry reachability
- real software execution paths

## 9. Refactoring Standard

Refactoring is encouraged when it improves:

- responsibility boundaries
- naming
- testability
- debuggability
- consistency between machines

Refactoring should be rejected when it:

- moves hot logic out of efficient implementations without justification
- merges unrelated responsibilities for convenience
- introduces production fallback paths that dilute the architecture
- weakens state/debug/test guarantees

The default preference is:

- shared cold-path helpers are good
- machine-specific hacks in generic layers are bad
- generic abstractions are good only when they are genuinely generic

Do not force abstraction early if the semantics are still machine-specific.

## 10. Release Standard

Before a release:

1. clean generated artifacts if needed
2. rebuild from scratch
3. run relevant automated tests
4. smoke test affected machines with real media
5. update changelog and TODO if scope changed

A release is ready when the shipped path is coherent, test-backed, and does not rely on accidental stale artifacts.
