"""启动脚本 - 确保 Windows 上使用 ProactorEventLoop"""
import sys
import asyncio
import os

# 关键：在导入 uvicorn 之前设置 ProactorEventLoop 策略
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uvicorn

if __name__ == "__main__":
    print("Starting PlayGen API server with ProactorEventLoop...")
    print(f"Event loop policy: {asyncio.get_event_loop_policy().__class__.__name__}")
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,  # reload 模式的子进程不继承事件循环策略
    )
