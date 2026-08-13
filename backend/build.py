"""Build the Vue frontend and package the desktop application with PyInstaller."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BACKEND_DIR.parent
FRONTEND_DIR = PROJECT_DIR / "frontend"
FRONTEND_DIST_DIR = FRONTEND_DIR / "dist"
STATIC_DIR = BACKEND_DIR / "static"
RELEASE_DIR = BACKEND_DIR / "release"
PYINSTALLER_WORK_DIR = BACKEND_DIR / "build" / "pyinstaller"
PYINSTALLER_SPEC_DIR = BACKEND_DIR / "build" / "spec"
DESKTOP_ENTRY = BACKEND_DIR / "desktop.py"
DEFAULT_APP_NAME = "FastAPI-Vue-Template"


def run_command(command: list[str], *, cwd: Path) -> None:
    """Run a child process and stop immediately when it fails."""
    print(f"> {' '.join(command)}")
    subprocess.run(command, cwd=cwd, check=True)


def build_frontend(*, skip_build: bool) -> None:
    """Build Vue and copy the generated files into the backend bundle folder."""
    if not skip_build:
        pnpm = shutil.which("pnpm")
        if pnpm is None:
            raise RuntimeError("pnpm was not found. Install pnpm and run `pnpm install` first.")
        run_command([pnpm, "build"], cwd=FRONTEND_DIR)

    index_file = FRONTEND_DIST_DIR / "index.html"
    if not index_file.is_file():
        raise RuntimeError(
            f"Frontend build not found at {index_file}. Run `pnpm build` in the frontend folder."
        )

    # Only this generated directory is replaced; source files and user data are untouched.
    if STATIC_DIR.resolve().parent != BACKEND_DIR.resolve():
        raise RuntimeError(f"Refusing to replace an unexpected directory: {STATIC_DIR}")
    if STATIC_DIR.exists():
        shutil.rmtree(STATIC_DIR)
    shutil.copytree(FRONTEND_DIST_DIR, STATIC_DIR)
    print(f"Prepared frontend assets: {STATIC_DIR}")


def pyinstaller_data_option(source: Path, destination: str) -> str:
    """Return PyInstaller's cross-platform SOURCE:DEST data-file syntax."""
    return f"{source.resolve().as_posix()}:{destination}"


def package_desktop(args: argparse.Namespace) -> Path:
    """Invoke PyInstaller with deterministic project-local output paths."""
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        f"--{args.mode}",
        "--console" if args.console else "--windowed",
        "--name",
        args.name,
        "--paths",
        str(BACKEND_DIR),
        "--add-data",
        pyinstaller_data_option(STATIC_DIR, "static"),
        "--distpath",
        str(RELEASE_DIR),
        "--workpath",
        str(PYINSTALLER_WORK_DIR),
        "--specpath",
        str(PYINSTALLER_SPEC_DIR),
    ]

    if args.icon is not None:
        icon = args.icon if args.icon.is_absolute() else BACKEND_DIR / args.icon
        icon = icon.resolve()
        if not icon.is_file():
            raise RuntimeError(f"Icon file not found: {icon}")
        command.extend(["--icon", str(icon)])

    command.append(str(DESKTOP_ENTRY))
    run_command(command, cwd=BACKEND_DIR)

    executable_name = f"{args.name}.exe" if sys.platform == "win32" else args.name
    if args.mode == "onefile":
        return RELEASE_DIR / executable_name
    return RELEASE_DIR / args.name / executable_name


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build Vue and package the FastAPI + PyWebView desktop application."
    )
    parser.add_argument(
        "--mode",
        choices=("onedir", "onefile"),
        default="onedir",
        help="Use onedir while testing; switch to onefile for final delivery.",
    )
    parser.add_argument("--name", default=DEFAULT_APP_NAME, help="Executable/application name.")
    parser.add_argument("--icon", type=Path, help="Optional Windows .ico file.")
    parser.add_argument(
        "--console",
        action="store_true",
        help="Keep a console window so startup and backend logs remain visible.",
    )
    parser.add_argument(
        "--skip-frontend-build",
        action="store_true",
        help="Reuse the existing frontend/dist after verifying it contains index.html.",
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Build/copy the frontend without invoking PyInstaller.",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Run the packaged executable without a GUI and verify its HTTP routes.",
    )
    args = parser.parse_args()

    if Path(args.name).name != args.name:
        parser.error("--name must be a file name, not a path")
    return args


def main() -> None:
    args = parse_args()
    build_frontend(skip_build=args.skip_frontend_build)

    if args.prepare_only:
        print("Frontend preparation completed; PyInstaller was not run.")
        return

    artifact = package_desktop(args)
    print(f"Desktop package created: {artifact}")
    if args.smoke_test:
        run_command([str(artifact), "--smoke-test"], cwd=artifact.parent)
        print("Packaged executable smoke test passed.")


if __name__ == "__main__":
    main()
