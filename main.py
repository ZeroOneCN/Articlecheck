# -*- coding: utf-8 -*-
"""程序入口。

保持「双击/命令行直接运行 main.py」的用法不变，内部委托给 app 包。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.ui.main_window import main

if __name__ == '__main__':
    main()
