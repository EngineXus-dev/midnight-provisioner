# Phase 16 — Script-mode test import path repair

> Privacy note: hardware and installation scenarios are illustrative. Discover actual device details independently; historical scenarios are not current authorization.

**Draft / No merges / No host deployment**

## Confirmed execution blocker

The three Nightglass test helpers are run as scripts:

```
python -B scripts/run_portable_suite.py --pattern test_kali_templates.py
python -B scripts/run_headless_matrix.py
python -B scripts/run_required_suite.py --check gui
```

Under ordinary Python behavior, executing a path inside `scripts/`
places **that scripts directory** on `sys.path`. unittest discovery
subsequently adds `tests/`, but not necessarily the repository root.
Nightglass test modules import from `nightglass`, a package located
at the project root. This can produce `ModuleNotFoundError:
No module named 'nightglass'` even when the checkout is intact.

This was reproduced in a disposable Python 3.13 project **before**
the fix, with `scripts/runner.py`, `tests/test_x.py` and a local
`nightglass/__init__.py`. The fixture's loader detected an import
error instead of running the test.

## Fix

All three helpers now explicitly put the validated, current
candidate's project root at the **front of `sys.path` before test
discovery**. They also remove one previously occurring copy of the
same root to avoid leaving it behind an inherited PYTHONPATH value.

The scripts still enforce their earlier restrictions:

- `run_portable_suite.py`: only explicitly allowlisted Windows
  test modules, at least one real passing test, rejects zero
  discovery / all skipped / failed imports
- `run_headless_matrix.py`: at least 60 collected cases and
  40 actually executed cases per Python 3.11/3.12/3.13 image
- `run_required_suite.py`: five actual executed GUI or native
  fixture tests, zero skipped cases, on explicitly selected
  environments

No target VM is started or software installed by these helpers.

## Runtime regression test

`tests/test_isolated_runner_imports.py` constructs a new
temporary, synthetic project that has its own `scripts/`,
`tests/` and `nightglass/` directories. It copies the actual
three checked-out runner scripts into that temporary project and
executes them as separate Python subprocesses with **PYTHONPATH
removed**. It verifies successful package imports, positive
case counts, and nonzero exit behavior if the package disappears.
A source regression additionally verifies that all three real
runners insert the project root before discovery.

The test is added to the Windows-portable allowlist and is also
included by the Python Docker headless-matrix test discovery.

### Evidence collected here

- **Pre-fix reproduced** on the local isolated Python 3.13
  environment: unittest discovery cannot find `nightglass`.
- **Post-fix core import-path logic exercised** in the same
  environment: synthetic script-mode runners successfully
  discovered and executed **65 / 75 / 5** representative
  passing tests, respectively.

These are synthetic, locally generated files. They do **not**
constitute a full execution of the new GitHub test file on the
private checkout, and they do not certify Windows-native behavior,
Fedora Qt/libvirt dependencies or physical KVM/sVirt security.

The exact private GitHub repository test suite, native Windows
PowerShell parser, Python 3.11–3.13 Docker matrix and Fedora 43
fixtures still require **explicit execution against the pinned
current candidate SHA**. Do not treat source-level or isolated
fixture results as release acceptance.

## Integration status

The predecessor snapshot includes **49 older draft PRs**
(#1–29 and #31–50; #30 absent). The active candidate branch is
`verification/phase16-isolated-import-paths`. The cumulative
runner, independent local evidence checker, stack verifier and
Windows PowerShell launcher all point at this candidate.

The original Windows 10 machine, Windows 11 Pro installation
planning, optional later activation, separate 16 GB USB,
example backup-drive capacity backup-only portable drive and Fedora dual-boot hardware
remain **unchanged**. No GitHub Actions, forced Git changes,
PR merges or installer operations have occurred.
