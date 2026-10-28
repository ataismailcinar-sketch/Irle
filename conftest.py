# -*- coding: utf-8 -*-
"""
Pytest kök conftest'i.
Hem proje kökü hem de src/ klasörünü Python path'ine ekler:
  - Proje kökü  → `import config`, `import modules.xxx` vb. çalışır
  - src/        → `from irle.domain.commands import ...` çalışır
"""

import sys
import os

_root = os.path.dirname(__file__)           # Irle/
_src  = os.path.join(_root, "src")           # Irle/src/

for _path in (_root, _src):
    if _path not in sys.path:
        sys.path.insert(0, _path)
