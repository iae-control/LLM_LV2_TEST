"""인메모리 데이터 저장소"""

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any

from backend.protocol import TC1001_Setup, TC1002_Material


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
        self.current_setup: Optional[TC1001_Setup] = None
        self.current_material: Optional[TC1002_Material] = None
        self.coils: Dict[str, CoilData] = {}
        self.connection_state: ConnectionState = ConnectionState.DISCONNECTED
        self.alive_count_tx: int = 0
        self.alive_count_rx: int = 0
        self.last_alive_rx_time: Optional[str] = None
        self.work_a: str = ""
        self.work_b: str = ""
        self.spl_connected_since: Optional[str] = None
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

    def update_winding(self, bundle_no: str, mtrl_no: str, line_no: str,
                       layer_count: int, layers: list):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if bundle_no not in self.coils:
            self.coils[bundle_no] = CoilData(
                bundle_no=bundle_no,
                mtrl_no=mtrl_no,
                line_no=line_no,
                created_at=now,
            )
        coil = self.coils[bundle_no]
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
            "spl_connected_since": self.spl_connected_since,
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
