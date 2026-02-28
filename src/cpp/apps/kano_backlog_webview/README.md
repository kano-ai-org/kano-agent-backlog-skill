# kano_backlog_webview (C++ Drogon)

Local-only backlog visualization service.

## Scope (MVP)

- Read canonical markdown backlog files under `_kano/backlog/products/*/items/`
- Read-only APIs:
  - `GET /healthz`
  - `GET /api/products`
  - `GET /api/items?product=<name>[&q=...]`
  - `GET /api/items/<id>?product=<name>`
  - `GET /api/tree?product=<name>`
  - `GET /api/kanban?product=<name>`
  - `GET /api/refresh[?product=<name>]`
- UI: product switcher + tree + kanban at `/`

## Security Defaults

- Binds to `127.0.0.1` only
- Product path constrained to configured products root
- No mutation endpoints

## Build (Linux)

```bash
cmake --preset linux-ninja-gcc
cmake --build --preset build-linux
./build/linux-ninja-gcc/apps/kano_backlog_webview/kano_backlog_webview
```

or

```bash
./scripts/build/build_linux_gcc.sh
```

## Build (Windows, Ninja + MSVC)

Use the C++ convention skill guidance to pin MSVC toolset before CMake if needed.

```bat
cmake --preset windows-ninja-msvc
cmake --build --preset build-windows
build\windows-ninja-msvc\apps\kano_backlog_webview\Debug\kano_backlog_webview.exe
```

or

```bat
scripts\build\build_win_ninja_msvc.bat
```

## Runtime Configuration

- Backlog products root:
  - default: `_kano/backlog/products`
  - env: `KANO_BACKLOG_PRODUCTS_ROOT`
  - arg: `--backlog-root <path>`
- Port:
  - default: `8787`
  - env: `KANO_WEBVIEW_PORT`
  - arg: `--port <number>`
