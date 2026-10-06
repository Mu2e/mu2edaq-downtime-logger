---
title: mu2edaq-downtime-logger install
group: monitoring
tier: A
audience: expert
summary: Installing, bootstrapping, testing and launching mu2edaq-downtime-logger
---

# Install — mu2edaq-downtime-logger

Pure Python package (setuptools, `pyproject.toml`); nothing is compiled. There is
no CMake build, no C/C++ library and no systemd unit.

## Requirements

| Item | Requirement | Source |
|---|---|---|
| Python | ≥ 3.9 (AlmaLinux 9 system `python3` is 3.9; CI runs only 3.10–3.12, DTL-010) | `pyproject.toml:10`, `.github/workflows/ci.yml:16` |
| Runtime packages | PySide6 ≥ 6.6, PyYAML ≥ 6.0, pyzmq ≥ 25, zeep ≥ 4.2, watchdog ≥ 3.0, SQLAlchemy ≥ 2.0 | `pyproject.toml:13-19`, `requirements.txt` |
| Optional | `psycopg2-binary` (extra `postgres`), `pytest`, `pytest-qt` (extra `dev`) | `pyproject.toml:28-36` |
| Optional | `mu2edaq-discovery` from the sibling checkout; not on PyPI, so not a declared dependency | `pyproject.toml:20-25`, `bootstrap.sh:58-62` |
| Display | an X11/Wayland/macOS session, or `QT_QPA_PLATFORM=offscreen` | `__main__.py:31`, `ci.yml:18` |
| Qt runtime libraries (Linux, headless) | `libegl1 libxkbcommon0 libdbus-1-3 libxcb-cursor0 libfontconfig1 libgl1` and the `libxcb-*` set listed in CI | `ci.yml:32-39` |

## Bootstrap

```bash
cd ~/mu2edaq-main/mu2edaq-downtime-logger
./bootstrap.sh            # venv in ./venv, pip/setuptools/wheel upgraded, pip install -e .
./bootstrap.sh --dev      # also pytest, pytest-qt
./bootstrap.sh --postgres # also psycopg2-binary
./bootstrap.sh --recreate # delete ./venv first
PYTHON=python3.11 ./bootstrap.sh   # choose the interpreter that creates the venv
```

`bootstrap.sh` installs `../mu2edaq-discovery` in editable mode first when that
directory exists (`bootstrap.sh:58-62`); without it the application runs and
simply does not announce itself. Options are documented in `bootstrap.sh(1)`.

Manual equivalent:

```bash
python3 -m venv venv && source venv/bin/activate
pip install -e ../mu2edaq-discovery      # optional
pip install -e '.[dev]'
```

## Configure

The application has no built-in default configuration; `--config` is required
(`__main__.py:17`). Start from `config/config.example.yaml`, replace the `daq01`
placeholders and paths with site values (DTL-006), and keep the result outside
the repository or under a new name. Lower `clear_threshold` below
`min(weight)/Σweight` (DTL-002). Key reference: `mu2edaq-downtime-logger.yaml(5)`.

`config/local.yaml` is a workstation test file (loopback UDP, `/tmp/daq-test`,
web view on 127.0.0.1:8001). The start script uses it when `--config` is not
given, which is also what `crs-app start downtime-logger` does (DTL-013).

## Run

```bash
./start-mu2edaq-downtime-logger.sh --config /path/to/site.yaml      # background, PID + log in package dir
./start-mu2edaq-downtime-logger.sh --config /path/to/site.yaml --foreground --log-level DEBUG
source venv/bin/activate && mu2edaq-downtime-logger -c /path/to/site.yaml
```

Then switch *Monitoring* on in the main window or tray; it is off after every
start (DTL-016). Stop with tray *Quit* or `kill -INT`; see `OPERATIONS.md` for
why `stop-mu2edaq-downtime-logger.sh`'s `SIGTERM` is not a clean stop (DTL-014).

## Test

```bash
./bootstrap.sh --dev
source venv/bin/activate
QT_QPA_PLATFORM=offscreen pytest -v        # 67 tests, pytest + pytest-qt
```

Per-module invocations as CI runs them: `.github/workflows/ci.yml:49-86`.

## Man pages

```bash
man -l man/man1/mu2edaq-downtime-logger.1
man -l man/man5/mu2edaq-downtime-logger.yaml.5
man -l man/man7/mu2edaq-downtime-logger-api.7
man -l man/man3/downtime_logger.3
```

Nothing installs them system-wide; several packages ship a `bootstrap.sh(1)`, so
copying `man/man1/*` into a shared `MANPATH` would collide.
