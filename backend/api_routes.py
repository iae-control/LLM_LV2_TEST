"""FastAPI REST API 라우터 + WebSocket — SPL 관점

SPL 클라이언트로서의 API:
  - L2에서 수신한 데이터 조회
  - 1101 권취상태 수동 전송
  - 자동 권취 시작/중지
  - 라인 가동상태 설정
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from pydantic import BaseModel

from backend.protocol import TC1101_WindingStatus
from backend.data_store import DataStore
from backend.ws_manager import WebSocketManager

logger = logging.getLogger(__name__)

router = APIRouter()

# 전역 참조 (main.py에서 주입)
_data_store: Optional[DataStore] = None
_ws_manager: Optional[WebSocketManager] = None
_tcp_client = None


def init_routes(data_store: DataStore, ws_manager: WebSocketManager, tcp_client):
    global _data_store, _ws_manager, _tcp_client
    _data_store = data_store
    _ws_manager = ws_manager
    _tcp_client = tcp_client


# --- Request Models ---

class WindingRequest(BaseModel):
    bundle_no: str = ""
    mtrl_no: str = ""
    line_no: str = "A"
    layer_count: int = 25
    layers: List[str] = []
    date: str = ""


class ResultChangeRequest(BaseModel):
    bundle_no: str = ""
    mtrl_no: str = ""
    line_no: str = "A"
    filenames: List[str] = []
    date: str = ""


class LineStatusRequest(BaseModel):
    work_a: str = "01"
    work_b: str = "01"


class AutoWindingRequest(BaseModel):
    layers: List[str] = []
    layer_count: int = 25


class AutoWindingEnabledRequest(BaseModel):
    enabled: bool = False


class AlivePausedRequest(BaseModel):
    paused: bool = False


# --- REST Endpoints ---

@router.post("/api/send-winding")
async def send_winding(req: WindingRequest):
    """TC 1101 권취상태 수동 전송"""
    layers = req.layers
    if len(layers) < 25:
        layers = layers + ["N"] * (25 - len(layers))
    layers = layers[:25]

    success = await _tcp_client.send_winding_status(
        bundle_no=req.bundle_no,
        mtrl_no=req.mtrl_no,
        line_no=req.line_no,
        layer_count=req.layer_count,
        layers=layers,
        date=req.date,
    )
    return {
        "success": success,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


@router.post("/api/send-result-change")
async def send_result_change(req: ResultChangeRequest):
    """TC 1010 판정결과 변경 수동 전송"""
    filenames = req.filenames
    if len(filenames) < 10:
        filenames = filenames + [""] * (10 - len(filenames))
    filenames = filenames[:10]

    success = await _tcp_client.send_result_change(
        bundle_no=req.bundle_no,
        mtrl_no=req.mtrl_no,
        line_no=req.line_no,
        filenames=filenames,
        date=req.date,
    )
    return {
        "success": success,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


@router.post("/api/toggle-alive")
async def toggle_alive(req: AlivePausedRequest):
    """Alive(1199) 발신 중단/재개"""
    _tcp_client.alive_paused = req.paused
    await _ws_manager.broadcast("alive_paused_changed", {"paused": req.paused})
    return {
        "success": True,
        "paused": req.paused,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


@router.post("/api/toggle-auto-winding-enabled")
async def toggle_auto_winding_enabled(req: AutoWindingEnabledRequest):
    """자동 권취 활성화/비활성화 (1002 수신 시 자동 1101 전송 여부)"""
    _data_store.auto_winding_enabled = req.enabled
    await _ws_manager.broadcast("auto_winding_enabled_changed", {"enabled": req.enabled})
    return {
        "success": True,
        "auto_winding_enabled": req.enabled,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


@router.post("/api/start-auto-winding")
async def start_auto_winding(req: AutoWindingRequest = None):
    """자동 권취 — 설정된 레이어 상태로 즉시 1101 전송 (1회)"""
    layers = req.layers if req and req.layers else None
    layer_count = req.layer_count if req else 25
    success = await _tcp_client.start_auto_winding(layers=layers, layer_count=layer_count)
    return {
        "success": success,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


@router.post("/api/stop-auto-winding")
async def stop_auto_winding():
    """자동 권취 진행 중 중지"""
    success = await _tcp_client.stop_auto_winding()
    return {
        "success": success,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


@router.post("/api/set-auto-winding-config")
async def set_auto_winding_config(req: AutoWindingRequest):
    """자동 권취 레이어 설정 저장 (1002 수신 시 사용될 설정)"""
    layers = req.layers if req.layers else ["N"] * 25
    if len(layers) < 25:
        layers = layers + ["N"] * (25 - len(layers))
    layers = layers[:25]
    _tcp_client.auto_winding_layers = layers
    _tcp_client.auto_winding_layer_count = req.layer_count
    await _ws_manager.broadcast("auto_winding_config_changed", {
        "layers": layers,
        "layer_count": req.layer_count,
    })
    return {
        "success": True,
        "layers": layers,
        "layer_count": req.layer_count,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


@router.post("/api/set-line-status")
async def set_line_status(req: LineStatusRequest):
    """A/B 라인 가동상태 설정 (1199 Alive에 포함됨)"""
    _data_store.work_a = req.work_a
    _data_store.work_b = req.work_b
    await _ws_manager.broadcast("line_status_changed", {
        "work_a": req.work_a,
        "work_b": req.work_b,
    })
    return {
        "work_a": req.work_a,
        "work_b": req.work_b,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


@router.get("/api/status")
async def get_status():
    """현재 접속/가동 상태"""
    status = _data_store.get_status()
    status["auto_winding_active"] = _tcp_client.auto_winding_active
    return status


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

    try:
        setup_data = None
        if _data_store.current_setup:
            s = _data_store.current_setup
            setup_data = {
                "dims_name": s.dims_name, "spec_cd": s.spec_cd,
                "mat_grade": s.mat_grade, "qtb_speed": s.qtb_speed,
                "spl_a_speed": s.spl_a_speed, "spl_b_speed": s.spl_b_speed,
            }
        material_data = None
        if _data_store.current_material:
            m = _data_store.current_material
            material_data = {
                "bundle_no": m.bundle_no, "mtrl_no": m.mtrl_no,
                "heat_no": m.heat_no, "spec_cd": m.spec_cd,
                "mat_grade": m.mat_grade, "dims_name": m.dims_name,
                "line_no": m.line_no,
            }
        result_change_data = None
        if _data_store.current_result_change:
            rc = _data_store.current_result_change
            result_change_data = {
                "bundle_no": rc.bundle_no, "mtrl_no": rc.mtrl_no,
                "line_no": rc.line_no, "date": rc.date,
                "filenames": rc.filenames,
            }

        await _ws_manager.send_personal(websocket, "init_state", {
            "status": _data_store.get_status(),
            "coils": _data_store.get_coils(),
            "logs": _data_store.get_logs(limit=50),
            "setup": setup_data,
            "material": material_data,
            "result_change": result_change_data,
            "auto_winding_active": _tcp_client.auto_winding_active,
            "auto_winding_layers": _tcp_client.auto_winding_layers,
            "auto_winding_layer_count": _tcp_client.auto_winding_layer_count,
            "alive_paused": _tcp_client.alive_paused,
        })
    except Exception:
        pass

    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        _ws_manager.disconnect(websocket)
    except Exception:
        _ws_manager.disconnect(websocket)
