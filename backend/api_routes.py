"""FastAPI REST API 라우터 + WebSocket 엔드포인트"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from pydantic import BaseModel

from backend.protocol import (
    TC1001_Setup, TC1002_Material, TC1010_ResultChange,
)
from backend.data_store import DataStore
from backend.ws_manager import WebSocketManager

logger = logging.getLogger(__name__)

router = APIRouter()

# 전역 참조 (main.py에서 주입)
_data_store: Optional[DataStore] = None
_ws_manager: Optional[WebSocketManager] = None
_tcp_server = None


def init_routes(data_store: DataStore, ws_manager: WebSocketManager, tcp_server):
    global _data_store, _ws_manager, _tcp_server
    _data_store = data_store
    _ws_manager = ws_manager
    _tcp_server = tcp_server


# --- Request Models ---

class SetupRequest(BaseModel):
    dims_name: str = ""
    spec_cd: str = ""
    mat_grade: str = ""
    qtb_speed: str = ""
    spl_a_speed: str = ""
    spl_b_speed: str = ""


class MaterialRequest(BaseModel):
    bundle_no: str = ""
    mtrl_no: str = ""
    heat_no: str = ""
    spec_cd: str = ""
    mat_grade: str = ""
    dims_name: str = ""
    line_no: str = "A"
    qtb_speed: str = ""
    spl_a_speed: str = ""
    spl_b_speed: str = ""
    qtb_temp: str = ""


class ResultChangeRequest(BaseModel):
    bundle_no: str = ""
    mtrl_no: str = ""
    line_no: str = "A"
    filenames: List[str] = []


# --- REST Endpoints ---

@router.post("/api/setup")
async def send_setup(req: SetupRequest):
    """생산정보 1001 전송"""
    pkt = TC1001_Setup(
        dims_name=req.dims_name,
        spec_cd=req.spec_cd,
        mat_grade=req.mat_grade,
        qtb_speed=req.qtb_speed,
        spl_a_speed=req.spl_a_speed,
        spl_b_speed=req.spl_b_speed,
    )
    raw = pkt.build()
    _data_store.current_setup = pkt

    success = await _tcp_server.send_packet(raw, "1001")
    return {
        "success": success,
        "packet_ascii": raw,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


@router.post("/api/material")
async def send_material(req: MaterialRequest):
    """소재정보 1002 전송"""
    pkt = TC1002_Material(
        bundle_no=req.bundle_no,
        mtrl_no=req.mtrl_no,
        heat_no=req.heat_no,
        spec_cd=req.spec_cd,
        mat_grade=req.mat_grade,
        dims_name=req.dims_name,
        line_no=req.line_no,
        qtb_speed=req.qtb_speed,
        spl_a_speed=req.spl_a_speed,
        spl_b_speed=req.spl_b_speed,
        qtb_temp=req.qtb_temp,
    )
    raw = pkt.build()
    _data_store.current_material = pkt

    # 코일 데이터에 소재정보 연결
    if req.bundle_no:
        if req.bundle_no not in _data_store.coils:
            from backend.data_store import CoilData
            _data_store.coils[req.bundle_no] = CoilData(
                bundle_no=req.bundle_no,
                created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )
        coil = _data_store.coils[req.bundle_no]
        coil.mtrl_no = req.mtrl_no
        coil.line_no = req.line_no
        coil.material_info = req.model_dump()

    success = await _tcp_server.send_packet(raw, "1002")
    return {
        "success": success,
        "packet_ascii": raw,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


@router.post("/api/result-change")
async def send_result_change(req: ResultChangeRequest):
    """판정결과 변경 1010 전송"""
    pkt = TC1010_ResultChange(
        bundle_no=req.bundle_no,
        mtrl_no=req.mtrl_no,
        line_no=req.line_no,
        filenames=req.filenames,
    )
    raw = pkt.build()

    success = await _tcp_server.send_packet(raw, "1010")
    return {
        "success": success,
        "packet_ascii": raw,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


@router.get("/api/status")
async def get_status():
    """현재 연결/가동 상태"""
    return _data_store.get_status()


@router.get("/api/coils")
async def get_coils():
    """코일(번들) 목록 + 권취상태"""
    return {"coils": _data_store.get_coils()}


@router.get("/api/logs")
async def get_logs(
    limit: int = Query(100, ge=1, le=1000),
    tc_filter: Optional[str] = Query(None),
    direction: Optional[str] = Query(None),
):
    """전문 송수신 로그"""
    return {"logs": _data_store.get_logs(limit=limit, tc_filter=tc_filter, direction=direction)}


# --- WebSocket Endpoint ---

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await _ws_manager.connect(websocket)

    # 연결 시 현재 상태 전체 push
    try:
        await _ws_manager.send_personal(websocket, "init_state", {
            "status": _data_store.get_status(),
            "coils": _data_store.get_coils(),
            "logs": _data_store.get_logs(limit=50),
        })
    except Exception:
        pass

    try:
        while True:
            # 프론트엔드로부터 메시지 수신 (keep-alive)
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        _ws_manager.disconnect(websocket)
    except Exception:
        _ws_manager.disconnect(websocket)
