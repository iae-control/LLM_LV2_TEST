"""asyncio TCP Server — L2 TCP Server (port 12147)

SPL 클라이언트 연결 수락, 전문 수신/파싱, Alive 관리.
TCP 스트림에서 고정길이 전문 단위로 정확히 잘라냄.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from backend.protocol import (
    TC_LENGTHS, TC_PARSERS,
    TC1001_Setup, TC1002_Material, TC1010_ResultChange,
    TC1099_Alive, TC1101_WindingStatus, TC1199_Alive,
)
from backend.data_store import DataStore, ConnectionState
from backend.ws_manager import WebSocketManager

logger = logging.getLogger(__name__)

# SPL → L2 방향 TC 코드 (서버가 수신하는 전문)
SPL_TO_L2_TC = {"1101", "1199"}


class L2TCPServer:
    def __init__(self, data_store: DataStore, ws_manager: WebSocketManager,
                 host: str = "0.0.0.0", port: int = 12147):
        self.host = host
        self.port = port
        self.data_store = data_store
        self.ws_manager = ws_manager

        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.server: Optional[asyncio.AbstractServer] = None

        self.alive_counter = 0
        self._alive_task: Optional[asyncio.Task] = None
        self._receive_task: Optional[asyncio.Task] = None
        self._alive_watchdog_task: Optional[asyncio.Task] = None
        self._last_alive_rx: Optional[float] = None
        self._running = False

    async def start(self):
        self.server = await asyncio.start_server(
            self._handle_client, self.host, self.port
        )
        self._running = True
        logger.info(f"TCP Server listening on {self.host}:{self.port}")

    async def stop(self):
        self._running = False
        if self._alive_task:
            self._alive_task.cancel()
        if self._receive_task:
            self._receive_task.cancel()
        if self._alive_watchdog_task:
            self._alive_watchdog_task.cancel()
        if self.writer:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception:
                pass
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        logger.info("TCP Server stopped")

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        peer = writer.get_extra_info("peername")
        logger.info(f"SPL client connected from {peer}")

        # 기존 연결이 있으면 정리
        if self.writer:
            try:
                self.writer.close()
            except Exception:
                pass

        self.reader = reader
        self.writer = writer
        self._last_alive_rx = asyncio.get_event_loop().time()

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.data_store.connection_state = ConnectionState.CONNECTED
        self.data_store.spl_connected_since = now

        await self.ws_manager.broadcast("connection_changed", {
            "state": ConnectionState.CONNECTED.value,
            "timestamp": now,
        })

        # Alive 발신 루프 시작
        if self._alive_task:
            self._alive_task.cancel()
        self._alive_task = asyncio.create_task(self._alive_send_loop())

        # Alive 감시 루프 시작
        if self._alive_watchdog_task:
            self._alive_watchdog_task.cancel()
        self._alive_watchdog_task = asyncio.create_task(self._alive_watchdog())

        # 수신 루프
        try:
            await self._receive_loop(reader)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Receive loop error: {e}")
        finally:
            await self._on_client_disconnected()

    async def _receive_loop(self, reader: asyncio.StreamReader):
        """TCP 스트림에서 전문 단위 파싱 루프"""
        while self._running:
            # 1. TC 코드 4바이트 읽기
            try:
                tc_bytes = await reader.readexactly(4)
            except asyncio.IncompleteReadError:
                logger.info("SPL client disconnected (incomplete read)")
                return
            except ConnectionError:
                logger.info("SPL client connection lost")
                return

            tc_code = tc_bytes.decode("ascii", errors="replace")

            # 2. TC 코드로 전문 총 길이 결정
            total_len = TC_LENGTHS.get(tc_code)
            if total_len is None:
                logger.warning(f"Unknown TC code: {tc_code}")
                continue

            # 3. 나머지 바이트 읽기
            try:
                remaining = await reader.readexactly(total_len - 4)
            except asyncio.IncompleteReadError:
                logger.info("SPL client disconnected during read")
                return
            except ConnectionError:
                logger.info("SPL client connection lost during read")
                return

            full_msg = tc_bytes.decode("ascii") + remaining.decode("ascii", errors="replace")

            # 4. 파싱 & 처리
            await self._dispatch(tc_code, full_msg)

    async def _dispatch(self, tc_code: str, raw: str):
        """수신 전문 라우팅"""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        parsed_data = {}

        try:
            parser = TC_PARSERS.get(tc_code)
            if parser:
                parsed_obj = parser(raw)
                parsed_data = self._obj_to_dict(parsed_obj)
        except Exception as e:
            logger.error(f"Parse error TC {tc_code}: {e}")

        # 로그 기록
        log = self.data_store.add_packet_log("RX", tc_code, raw, parsed_data)
        await self.ws_manager.broadcast("packet_log", {
            "direction": "RX", "tc": tc_code, "raw": raw,
            "parsed": parsed_data, "timestamp": now_str,
        })

        if tc_code == "1101":
            await self._handle_winding(raw, parsed_data)
        elif tc_code == "1199":
            await self._handle_alive_rx(raw, parsed_data)
        else:
            logger.info(f"RX TC={tc_code} ({len(raw)}B)")

    async def _handle_winding(self, raw: str, parsed: dict):
        """TC 1101 권취상태 수신 처리"""
        try:
            obj = TC1101_WindingStatus.parse(raw)
            self.data_store.update_winding(
                bundle_no=obj.bundle_no,
                mtrl_no=obj.mtrl_no,
                line_no=obj.line_no,
                layer_count=obj.layer_count,
                layers=obj.layers,
            )
            await self.ws_manager.broadcast("winding_status", {
                "bundle_no": obj.bundle_no,
                "mtrl_no": obj.mtrl_no,
                "line_no": obj.line_no,
                "layer_count": obj.layer_count,
                "layers": [
                    {"index": i + 1, "status": obj.layers[i]}
                    for i in range(25)
                ],
            })
            logger.info(f"RX TC=1101 bundle={obj.bundle_no} layers={obj.layer_count}")
        except Exception as e:
            logger.error(f"Handle winding error: {e}")

    async def _handle_alive_rx(self, raw: str, parsed: dict):
        """TC 1199 SPL Alive 수신 처리"""
        try:
            obj = TC1199_Alive.parse(raw)
            self._last_alive_rx = asyncio.get_event_loop().time()
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            self.data_store.alive_count_rx = obj.count
            self.data_store.last_alive_rx_time = now_str
            self.data_store.work_a = obj.work_a
            self.data_store.work_b = obj.work_b

            if self.data_store.connection_state != ConnectionState.ALIVE_OK:
                self.data_store.connection_state = ConnectionState.ALIVE_OK
                await self.ws_manager.broadcast("connection_changed", {
                    "state": ConnectionState.ALIVE_OK.value,
                    "timestamp": now_str,
                })

            await self.ws_manager.broadcast("alive_received", {
                "count": obj.count,
                "work_a": obj.work_a,
                "work_b": obj.work_b,
                "timestamp": now_str,
            })
            logger.debug(f"RX TC=1199 cnt={obj.count} A={obj.work_a} B={obj.work_b}")
        except Exception as e:
            logger.error(f"Handle alive RX error: {e}")

    async def _alive_send_loop(self):
        """30초 주기 TC 1099 Alive 발신"""
        try:
            while self._running and self.writer:
                await asyncio.sleep(30)
                if not self.writer:
                    break
                self.alive_counter = (self.alive_counter + 1) % 10000
                pkt = TC1099_Alive(count=self.alive_counter)
                await self.send_packet(pkt.build(), "1099")
                self.data_store.alive_count_tx = self.alive_counter
        except asyncio.CancelledError:
            pass

    async def _alive_watchdog(self):
        """SPL Alive(1199) 수신 감시: 90초 타임아웃"""
        try:
            while self._running:
                await asyncio.sleep(10)
                if self._last_alive_rx is None:
                    continue
                elapsed = asyncio.get_event_loop().time() - self._last_alive_rx
                if elapsed > 90:
                    if self.data_store.connection_state != ConnectionState.ALIVE_TIMEOUT:
                        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        self.data_store.connection_state = ConnectionState.ALIVE_TIMEOUT
                        await self.ws_manager.broadcast("connection_changed", {
                            "state": ConnectionState.ALIVE_TIMEOUT.value,
                            "timestamp": now_str,
                        })
                        logger.warning("SPL Alive timeout (>90s)")
        except asyncio.CancelledError:
            pass

    async def send_packet(self, raw: str, tc_code: str = None):
        """TCP로 전문 전송 + 로그"""
        if not self.writer:
            logger.warning("Cannot send: no SPL client connected")
            return False

        try:
            self.writer.write(raw.encode("ascii"))
            await self.writer.drain()
        except Exception as e:
            logger.error(f"Send error: {e}")
            return False

        if tc_code is None:
            tc_code = raw[0:4] if len(raw) >= 4 else "????"

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        parsed_data = {}
        try:
            parser = TC_PARSERS.get(tc_code)
            if parser:
                parsed_data = self._obj_to_dict(parser(raw))
        except Exception:
            pass

        self.data_store.add_packet_log("TX", tc_code, raw, parsed_data)
        await self.ws_manager.broadcast("packet_log", {
            "direction": "TX", "tc": tc_code, "raw": raw,
            "parsed": parsed_data, "timestamp": now_str,
        })
        logger.debug(f"TX TC={tc_code} ({len(raw)}B)")
        return True

    async def _on_client_disconnected(self):
        """클라이언트 연결 종료 처리"""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.data_store.connection_state = ConnectionState.DISCONNECTED
        self.data_store.spl_connected_since = None
        self.writer = None
        self.reader = None

        if self._alive_task:
            self._alive_task.cancel()
            self._alive_task = None
        if self._alive_watchdog_task:
            self._alive_watchdog_task.cancel()
            self._alive_watchdog_task = None

        await self.ws_manager.broadcast("connection_changed", {
            "state": ConnectionState.DISCONNECTED.value,
            "timestamp": now_str,
        })
        logger.info("SPL client disconnected")

    @staticmethod
    def _obj_to_dict(obj) -> dict:
        """dataclass → dict (직렬화용)"""
        result = {}
        for k, v in obj.__dict__.items():
            if isinstance(v, list):
                result[k] = v
            else:
                result[k] = str(v) if v is not None else ""
        return result

    @property
    def is_connected(self) -> bool:
        return self.writer is not None
