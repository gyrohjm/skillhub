#!/usr/bin/env python3
"""Project context and document routing for the DFT skill suite."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "dft-contracts"))
from dft_contracts.project import main

if __name__ == "__main__":
    raise SystemExit(main())
