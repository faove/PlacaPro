"""Benchmark del optimizador: placas, aprovechamiento y tiempo por nivel.

Uso: ``python scripts/benchmark.py [--write]`` (``--write`` actualiza docs/benchmarks.md).
Las instancias son listas de muebles sintéticas, reproducibles por semilla.

``--write`` regenera la tabla y conserva las secciones ``## …`` escritas a mano.
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from models.parametros import CuttingParameters, OptimizationLevel  # noqa: E402
from models.pieza import PieceSpec, expand_pieces  # noqa: E402
from models.placa import PlateFormat  # noqa: E402
from optimization.optimizer import OptimizationRequest, Optimizer  # noqa: E402
from optimization.verification import verify_result  # noqa: E402

SIZES = (20, 50, 100, 200)


def instance(n_pieces: int, seed: int) -> list[PieceSpec]:
    """Piezas típicas de muebles: laterales, estantes, puertas, frentes y zócalos."""
    rng = random.Random(seed)
    kinds = [
        lambda: (rng.randint(300, 600), rng.randint(600, 2200)),  # laterales
        lambda: (rng.randint(400, 1200), rng.randint(250, 600)),  # tapas, estantes
        lambda: (rng.randint(250, 600), rng.randint(400, 2000)),  # puertas
        lambda: (rng.randint(300, 900), rng.randint(80, 250)),  # frentes, zócalos
    ]
    specs: list[PieceSpec] = []
    total = 0
    i = 0
    while total < n_pieces:
        w, h = rng.choice(kinds)()
        qty = min(rng.choice([1, 1, 2, 2, 4]), n_pieces - total)
        specs.append(PieceSpec.from_mm(f"P{i}", qty, w, h, 18))
        total += qty
        i += 1
    return specs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="actualiza docs/benchmarks.md")
    args = parser.parse_args()

    plate = PlateFormat.from_mm("Melamina 1830 × 2820", 1830, 2820, 18)
    rows = []
    for n in SIZES:
        pieces = expand_pieces(instance(n, seed=n))
        for level in OptimizationLevel:
            params = CuttingParameters(level=level)
            opt = Optimizer(OptimizationRequest(pieces, plate, params))
            t0 = time.perf_counter()
            result = opt.run()
            elapsed = time.perf_counter() - t0
            ok = not verify_result(result, pieces, plate.grain)
            rows.append(
                (
                    n,
                    level.label,
                    result.lower_bound,
                    result.sheets_count,
                    f"{result.utilization:.1%}",
                    opt.attempts,
                    f"{elapsed:.2f}",
                    "sí" if ok else "NO",
                )
            )
            print(*rows[-1], sep="\t", flush=True)

    if args.write:
        header = (
            "| Piezas | Nivel | Cota inferior | Placas | Aprovechamiento | Intentos | Tiempo (s) "
            "| Verificado |\n|---:|---|---:|---:|---:|---:|---:|---|\n"
        )
        body = "\n".join("| " + " | ".join(map(str, r)) + " |" for r in rows)
        text = (
            "# Benchmarks del optimizador\n\n"
            f"Generado con `python scripts/benchmark.py --write` el {date.today().isoformat()} "
            f"(Python {sys.version.split()[0]}).\n\n"
            "Placa 1830 × 2820 mm, kerf 3,2 mm, margen 10 mm, modo escuadradora. Instancias "
            "sintéticas de piezas de muebles (semilla = nº de piezas).\n\n"
            "La *cota inferior* es ⌈Σ área inflada / área útil⌉. Solo considera áreas, así que "
            "con piezas grandes suele ser inalcanzable: llegar a ella demuestra el óptimo, pero "
            "no llegar no demuestra lo contrario.\n\n" + header + body + "\n"
        )
        path = ROOT / "docs" / "benchmarks.md"
        previous = path.read_text(encoding="utf-8") if path.exists() else ""
        manual = previous.find("\n## ")
        if manual >= 0:
            text += previous[manual:]
        path.write_text(text, encoding="utf-8")
        print("docs/benchmarks.md actualizado")


if __name__ == "__main__":
    main()
