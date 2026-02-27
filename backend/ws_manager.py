"""WebSocket 매니저 — 프론트엔드 실시간 이벤트 푸시"""

import asyncio
import json
import logging
from typing import Set, Any, Dict
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"WS client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        logger.info(f"WS client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, event_type: str, data: Dict[str, Any]):
        """모든 연결된 WS 클라이언트에 이벤트 브로드캐스트"""
        if not self.active_connections:
            return
        message = json.dumps({"type": event_type, "data": data}, ensure_ascii=False)
        disconnected = set()
        for ws in self.active_connections:
            try:
                await ws.send_text(message)
            except Exception:
                disconnected.add(ws)
        for ws in disconnected:
            self.active_connections.discard(ws)

    async def send_personal(self, websocket: WebSocket, event_type: str, data: Dict[str, Any]):
        """특정 클라이언트에 이벤트 전송"""
        message = json.dumps({"type": event_type, "data": data}, ensure_ascii=False)
        try:
            await websocket.send_text(message)
        except Exception:
            self.active_connections.discard(websocket)
