"""동국제강 CS공장 권취상태 모니터링 SPL 시스템 — Backend 엔트리포인트

SPL TCP Client (→ L2:12147) + FastAPI REST/WebSocket (port 8080)을
동일 asyncio 이벤트 루프에서 실행한다.
"""

import argparse
import asyncio
import logging
import sys
import os
from contextlib import asynccontextmanager

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uvicorn
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from backend.data_store import DataStore
from backend.ws_manager import WebSocketManager
from backend.tcp_client import SPLTCPClient
from backend.api_routes import router, init_routes

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# CLI 인자
parser = argparse.ArgumentParser(description="SPL Winding Monitor Backend")
parser.add_argument("--l2-host", default="127.0.0.1", help="L2 서버 IP (default: 127.0.0.1)")
parser.add_argument("--l2-port", type=int, default=12147, help="L2 서버 PORT (default: 12147)")
parser.add_argument("--api-port", type=int, default=8080, help="REST/WS API PORT (default: 8080)")
args, _ = parser.parse_known_args()

# 공유 인스턴스
data_store = DataStore()
ws_manager = WebSocketManager()
tcp_client = SPLTCPClient(data_store, ws_manager, host=args.l2_host, port=args.l2_port)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await tcp_client.start()
    logger.info(f"SPL Client connecting to L2 at {args.l2_host}:{args.l2_port}")
    logger.info(f"API Server running on http://0.0.0.0:{args.api_port}")
    yield
    # Shutdown
    await tcp_client.stop()
    logger.info("Server shutdown complete")


# FastAPI 앱
app = FastAPI(title="SPL Winding Monitor", version="2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록 & 의존성 주입
init_routes(data_store, ws_manager, tcp_client)
app.include_router(router)

# 프론트엔드 HTML 서빙
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@app.get("/")
async def serve_frontend():
    return FileResponse(FRONTEND_DIR / "index.html", media_type="text/html")


def main():
    print("=" * 50)
    print("  SPL Winding Status Monitor")
    print(f"  L2 Server : {args.l2_host}:{args.l2_port}")
    print(f"  API Server: http://0.0.0.0:{args.api_port}")
    print("=" * 50)

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=args.api_port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
