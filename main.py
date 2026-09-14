import sys
from pathlib import Path

src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from src.cli.commands import main

if __name__ == "__main__":
    sys.exit(main())