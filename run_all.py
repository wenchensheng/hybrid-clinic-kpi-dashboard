"""Run the full pipeline end to end: fetch CMS -> generate synthetic data -> clean -> SQLite + KPI SQL
-> dashboard JSON -> execute the analysis notebook (outputs saved in place).

Usage:  python run_all.py            # everything
        python run_all.py --skip-notebook
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

import build_db, clean, export_dashboard, fetch_cms, generate_synthetic  # noqa: E402


def execute_notebook(path: Path) -> None:
    import nbformat
    from nbclient import NotebookClient

    nb = nbformat.read(path, as_version=4)
    NotebookClient(nb, timeout=600, kernel_name="python3", resources={"metadata": {"path": str(path.parent)}}).execute()
    for cell in nb.cells:  # drop per-run timestamps so re-runs produce clean diffs
        cell.get("metadata", {}).pop("execution", None)
    nbformat.write(nb, path)
    print(f"[notebook] executed {path.relative_to(ROOT)} with outputs saved")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--skip-notebook", action="store_true")
    args = ap.parse_args()
    t0 = time.perf_counter()
    fetch_cms.main()
    generate_synthetic.main()
    clean.run()
    build_db.build()
    export_dashboard.main()
    if not args.skip_notebook:
        execute_notebook(ROOT / "notebooks" / "analysis.ipynb")
    print(f"[done] pipeline finished in {time.perf_counter() - t0:.1f}s. Open docs/index.html via `make serve`.")


if __name__ == "__main__":
    main()
