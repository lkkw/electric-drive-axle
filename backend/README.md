# Backend

FastAPI backend managed by [uv](https://docs.astral.sh/uv/). The importable
package is `app`, so run Uvicorn with `app.main:app` from this directory.

```powershell
uv sync
uv run main.py
```

API documentation is available at <http://127.0.0.1:8000/docs>.

`main.py` is a local development launcher. The importable ASGI application
remains `app.main:app`, so production processes can still use:

```powershell
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Optional Windows desktop package

The normal web workflow does not install desktop tooling. To build the Vue app,
serve it from FastAPI, and package everything with PyWebView/PyInstaller:

```powershell
uv sync --group desktop
uv run --group desktop python build.py --mode onedir --console --smoke-test
```

After testing the directory build, create the final single executable:

```powershell
uv run --group desktop python build.py --mode onefile
```

`desktop.py` is the packaged entry point. It reserves an OS-assigned loopback
port, starts Uvicorn in a background thread, waits for startup, and keeps the
PyWebView GUI loop on the main thread. Generated files are written under
`static/`, `build/`, and `release/`.
