import sys
import pathlib

# Ensure the repo root is on sys.path so tests can import 'node9'
# whether or not the package is installed.
sys.path.insert(0, str(pathlib.Path(__file__).parent))
