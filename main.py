"""项目根目录启动入口。

在 PyCharm / 命令行里直接运行 `main.py` 或 `uvicorn main:app` 即可启动整个后端，
无需手动 cd 到 backend。
"""
import sys
import os
from pathlib import Path

ROOT = Path(__file__).parent
BACKEND = ROOT / "backend"

# 切到 backend 目录：这样 .env、uploads/、相对路径资源都能正确找到
os.chdir(BACKEND)
# 把 backend 加入模块搜索路径，才能 import app.main
sys.path.insert(0, str(BACKEND))

from app.main import app  # noqa: E402

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
