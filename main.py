# -*- coding: utf-8 -*-
"""程序入口。

双击或 ``python main.py`` 都能跑，内部委托给 ``app`` 包。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.main_window import main

if __name__ == '__main__':
    main()
