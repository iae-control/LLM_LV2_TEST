"""인메모리 데이터 저장소 — SPL 관점"""

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any

from backend.protocol import TC1001_Setup, TC1002_Material, TC1010_ResultChange


class ConnectionState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTED = "connected"
    ALIVE_OK = "alive_ok"
    ALIVE_TIMEOUT = "alive_timeout"


@dataclass
class AliveRecord:
    timestamp: str
    direction: str   # "TX" or "RX"
    tc: str          # "1099" or "1199"
    count: int
    work_a: str = ""
    work_b: str = ""


@dataclass
class PacketLog:
    timestamp: str
    direction: str   # "TX" or "RX"
    tc: str
    raw_ascii: str
    parsed: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LayerInfo:
    index: int
    status: str
    updated_at: str = ""


@dataclass
class CoilData:
    bundle_no: str
    mtrl_no: str = ""
    line_no: str = ""
    layers: List[LayerInfo] = field(default_factory=list)
    layer_count: int = 0
    setup_info: Optional[Dict[str, Any]] = None
    material_info: Optional[Dict[str, Any]] = None
    created_at: str = ""
    updated_at: str = ""


class DataStore:
    def __init__(self):
        # L2에서 수신한 데이터
        self.current_setup: Optional[TC1001_Setup] = None
        self.current_material: Optional[TC1002_Material] = None
        self.current_result_change: Optional[TC1010_ResultChange] = None

        # 우리(SPL)가 보내는 권취 데이터
        self.coils: Dict[str, CoilData] = {}

        # L2 접속 상태
        self.connection_state: ConnectionState = ConnectionState.DISCONNECTED
        self.l2_connected_since: Optional[str] = None

        # Alive 카운터
        self.alive_count_tx: int = 0   # 우리 1199 발신 횟수
        self.alive_count_rx: int = 0   # L2 1099 수신 횟수
        self.last_alive_rx_time: Optional[str] = None

        # 우리(SPL) 라인 가동상태 (1199에 포함)
        self.work_a: str = "01"
        self.work_b: str = "01"

        # 자동 권취 제어 (1002 수신 시 자동 1101 전송 여부)
        self.auto_winding_enabled: bool = False

        # 로그
        self.alive_history: deque = deque(maxlen=100)
        self.packet_logs: deque = deque(maxlen=1000)

    def add_packet_log(self, direction: str, tc: str, raw_ascii: str, parsed: dict = None):
        log = PacketLog(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            direction=direction,
            tc=tc,
            raw_ascii=raw_ascii,
            parsed=parsed or {},
        )
        self.packet_logs.appendleft(log)
        return log

    def update_coil_from_material(self, material: TC1002_Material):
        """소재정보(1002) 수신 시 코일 데이터 생성/갱신"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        bn = material.bundle_no.strip()
        if not bn:
            return
        if bn not in self.coils:
            self.coils[bn] = CoilData(bundle_no=bn, created_at=now)
        coil = self.coils[bn]
        coil.mtrl_no = material.mtrl_no
        coil.line_no = material.line_no
        coil.material_info = {
            "bundle_no": material.bundle_no,
            "mtrl_no": material.mtrl_no,
            "heat_no": material.heat_no,
            "spec_cd": material.spec_cd,
            "mat_grade": material.mat_grade,
            "dims_name": material.dims_name,
            "line_no": material.line_no,
        }
        coil.updated_at = now

    def update_winding(self, bundle_no: str, mtrl_no: str, line_no: str,
                       layer_count: int, layers: list):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        bn = bundle_no.strip()
        if not bn:
            bn = bundle_no
        if bn not in self.coils:
            self.coils[bn] = CoilData(
                bundle_no=bn,
                mtrl_no=mtrl_no,
                line_no=line_no,
                created_at=now,
            )
        coil = self.coils[bn]
        coil.mtrl_no = mtrl_no
        coil.line_no = line_no
        coil.layer_count = layer_count
        coil.updated_at = now
        coil.layers = [
            LayerInfo(index=i + 1, status=layers[i], updated_at=now)
            for i in range(len(layers))
        ]

    def get_status(self) -> dict:
        return {
            "connection_state": self.connection_state.value,
            "alive_count_tx": self.alive_count_tx,
            "alive_count_rx": self.alive_count_rx,
            "last_alive_rx_time": self.last_alive_rx_time,
            "work_a": self.work_a,
            "work_b": self.work_b,
            "l2_connected_since": self.l2_connected_since,
            "auto_winding_enabled": self.auto_winding_enabled,
        }

    def get_coils(self) -> list:
        result = []
        for bn, coil in self.coils.items():
            result.append({
                "bundle_no": coil.bundle_no,
                "mtrl_no": coil.mtrl_no,
                "line_no": coil.line_no,
                "layer_count": coil.layer_count,
                "layers": [
                    {"index": l.index, "status": l.status, "updated_at": l.updated_at}
                    for l in coil.layers
                ],
                "setup_info": coil.setup_info,
                "material_info": coil.material_info,
                "created_at": coil.created_at,
                "updated_at": coil.updated_at,
            })
        return result

    def get_logs(self, limit: int = 100, tc_filter: str = None, direction: str = None) -> list:
        logs = list(self.packet_logs)
        if tc_filter:
            logs = [l for l in logs if l.tc == tc_filter]
        if direction:
            logs = [l for l in logs if l.direction == direction.upper()]
        return [
            {
                "timestamp": l.timestamp,
                "direction": l.direction,
                "tc": l.tc,
                "raw_ascii": l.raw_ascii,
                "parsed": l.parsed,
            }
            for l in logs[:limit]
        ]
