"""Pytest 全局配置。

必须在导入 ``app`` 之前把数据目录指向临时目录，防止测试改写开发机
%APPDATA% 下真实的安全阈值配置。
"""

import os
import tempfile

os.environ["AXLE_DATA_DIR"] = tempfile.mkdtemp(prefix="axle-test-")
