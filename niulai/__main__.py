# -*- coding: utf-8 -*-
"""niulai 包入口：python -m niulai <cmd>。"""
import sys

from .cli import main

if __name__ == '__main__':
    sys.exit(main())
