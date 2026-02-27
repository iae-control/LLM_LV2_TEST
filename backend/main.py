"""동국제강 CS공장 권취상태 모니터링 LV2 시스템 — Backend 엔트리포인트

TCP Server (port 12147) + FastAPI REST/WebSocket (port 8080)을
동일 asyncio 이벤트 루프에서 실행한다.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.data_store import DataStore
from backend.ws_manager import WebSocketManager
from backend.tcp_server import L2TCPServer
from backend.api_routes import router, init_routes

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# 공유 인스턴스
data_store = DataStore()
ws_manager = WebSocketManager()
tcp_server = L2TCPServer(data_store, ws_manager)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await tcp_server.start()
    logger.info("TCP Server listening on 0.0.0.0:12147")
    logger.info("API Server running on http://0.0.0.0:8080")
    yield
    # Shutdown
    await tcp_server.stop()
    logger.info("Server shutdown complete")


# FastAPI 앱
app = FastAPI(title="LV2 Monitoring System", version="1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록 & 의존성 주입
init_routes(data_store, ws_manager, tcp_server)
app.include_router(router)


def main():
    print("=" * 50)
    print("  LV2 Winding Status Monitoring System")
    print("  TCP Server: 0.0.0.0:12147")
    print("  API Server: http://0.0.0.0:8080")
    print("=" * 50)

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8080,
        log_level="info",
    )


if __name__ == "__main__":
    main()
