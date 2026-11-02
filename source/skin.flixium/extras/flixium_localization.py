"""Make the shared skin string lookup available to standalone skin scripts."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'resources/lib'))
from localization import localize

__all__ = ['localize']
