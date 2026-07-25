"""Levanta backend (uvicorn :8000) y frontend (vite :5173) a la vez.

Uso, desde la raíz del monorepo:

    python dev.py

Ctrl+C detiene ambos procesos.
"""

import shutil
import subprocess
import sys
import threading
from pathlib import Path

# La consola de Windows suele usar cp1252 y no soporta los caracteres que imprime Vite.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
ES_WINDOWS = sys.platform == "win32"

VENV_PYTHON = BACKEND / (".venv/Scripts/python.exe" if ES_WINDOWS else ".venv/bin/python")


def verificar_prerequisitos() -> None:
    errores = []
    if not VENV_PYTHON.exists():
        errores.append(
            f"No existe el venv del backend ({VENV_PYTHON}).\n"
            '  Créalo con: cd backend && python -m venv .venv && pip install -e ".[dev]"'
        )
    if not (FRONTEND / "node_modules").exists():
        errores.append(
            "No están instaladas las dependencias del frontend.\n"
            "  Instálalas con: cd frontend && npm install"
        )
    if errores:
        print("No se puede arrancar:\n", file=sys.stderr)
        for e in errores:
            print(f"- {e}\n", file=sys.stderr)
        sys.exit(1)


def levantar_db_local() -> None:
    if shutil.which("docker") is None:
        print("Docker no está disponible: la BD local no se levanta (opcional, ver README).")
        return

    print("Levantando BD local (docker compose) — puede tardar la primera vez (descarga la imagen)…")
    try:
        resultado = subprocess.run(
            ["docker", "compose", "up", "-d", "db"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        print("No se pudo levantar la BD local: docker compose tardó demasiado (opcional, continuando).")
        return
    except Exception as exc:
        print(f"No se pudo levantar la BD local: {exc} (opcional, continuando).")
        return

    if resultado.returncode == 0:
        print("BD local (postgres 17) arriba — docker compose up -d db")
    else:
        motivo = (resultado.stderr or resultado.stdout or "error desconocido").strip().splitlines()[-1]
        print(f"No se pudo levantar la BD local: {motivo} (opcional, continuando).")


def lanzar(nombre: str, comando: list[str], cwd: Path) -> subprocess.Popen:
    proc = subprocess.Popen(
        comando,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    def volcar_salida() -> None:
        for linea in proc.stdout:
            print(f"[{nombre}] {linea}", end="", flush=True)

    threading.Thread(target=volcar_salida, daemon=True).start()
    return proc


def detener(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if ES_WINDOWS:
        # terminate() no mata los hijos de npm.cmd; taskkill /T sí baja el árbol completo.
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def main() -> None:
    verificar_prerequisitos()
    levantar_db_local()
    npm = shutil.which("npm")
    if npm is None:
        print("No se encontró npm en el PATH.", file=sys.stderr)
        sys.exit(1)

    print("Levantando backend en http://localhost:8000 y frontend en http://localhost:5173")
    print("Ctrl+C para detener ambos.\n")

    procesos = [
        lanzar("backend", [str(VENV_PYTHON), "-m", "uvicorn", "app.main:app", "--reload", "--port", "8000"], BACKEND),
        lanzar("frontend", [npm, "run", "dev"], FRONTEND),
    ]

    codigo_salida = 0
    try:
        # Si un proceso muere, se detiene también el otro.
        while all(p.poll() is None for p in procesos):
            threading.Event().wait(0.5)
        caido = next(p for p in procesos if p.poll() is not None)
        print(f"\nUn proceso terminó inesperadamente (código {caido.returncode}); deteniendo el resto.")
        codigo_salida = caido.returncode or 1
    except KeyboardInterrupt:
        print("\nDeteniendo backend y frontend…")
    finally:
        for p in procesos:
            detener(p)
    sys.exit(codigo_salida)


if __name__ == "__main__":
    main()
