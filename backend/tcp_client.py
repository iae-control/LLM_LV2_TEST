"""SPL TCP Client — L2 서버에 접속하는 SPL 클라이언트

L2 서버에 TCP 클라이언트로 접속하여:
  - Alive(1199) 30초 주기 발신
  - L2로부터 1001, 1002, 1010, 1099 수신 & 파싱
  - 소재정보(1002) 수신 시 자동 권취 시작
  - 1101 권취상태 발신
"""

import asyncio
import logging
import random
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


class SPLTCPClient:
    def __init__(self, data_store: DataStore, ws_manager: WebSocketManager,
                 host: str = "127.0.0.1", port: int = 12147):
        self.host = host
        self.port = port
        self.data_store = data_store
        self.ws_manager = ws_manager

        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None

        self.alive_counter = 0
        self._alive_task: Optional[asyncio.Task] = None
        self._receive_task: Optional[asyncio.Task] = None
        self._alive_watchdog_task: Optional[asyncio.Task] = None
        self._reconnect_task: Optional[asyncio.Task] = None
        self._last_alive_rx: Optional[float] = None
        self._running = False

        # 자동 권취
        self._auto_winding_task: Optional[asyncio.Task] = None
        self._winding_layers: list = []
        self._winding_interval = (2.0, 5.0)

    async def start(self):
        """시작: L2 서버에 접속 시도"""
        self._running = True
        self._reconnect_task = asyncio.create_task(self._connect_loop())

    async def stop(self):
        """정지"""
        self._running = False
        for task in [self._alive_task, self._receive_task,
                     self._alive_watchdog_task, self._reconnect_task,
                     self._auto_winding_task]:
            if task:
                task.cancel()
        if self.writer:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception:
                pass
        logger.info("SPL TCP Client stopped")

    async def _connect_loop(self):
        """자동 재접속 루프"""
        while self._running:
            if not self.writer:
                try:
                    await self._connect()
                except (ConnectionRefusedError, OSError) as e:
                    logger.warning(f"L2 접속 실패: {e} (5초 후 재시도)")
                    await asyncio.sleep(5)
                    continue
                except asyncio.CancelledError:
                    return
            await asyncio.sleep(1)

    async def _connect(self):
        """L2 서버에 접속"""
        self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
        logger.info(f"L2 서버 접속 성공: {self.host}:{self.port}")

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.data_store.connection_state = ConnectionState.CONNECTED
        self.data_store.l2_connected_since = now

        self._last_alive_rx = asyncio.get_event_loop().time()

        await self.ws_manager.broadcast("connection_changed", {
            "state": ConnectionState.CONNECTED.value,
            "timestamp": now,
        })

        # Alive 발신 루프 (1199)
        if self._alive_task:
            self._alive_task.cancel()
        self._alive_task = asyncio.create_task(self._alive_send_loop())

        # Alive 감시
        if self._alive_watchdog_task:
            self._alive_watchdog_task.cancel()
        self._alive_watchdog_task = asyncio.create_task(self._alive_watchdog())

        # 수신 루프
        try:
            await self._receive_loop()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Receive loop error: {e}")
        finally:
            await self._on_disconnected()

    async def _receive_loop(self):
        """TCP 스트림에서 전문 단위 파싱 루프"""
        while self._running and self.reader:
            try:
                tc_bytes = await self.reader.readexactly(4)
            except (asyncio.IncompleteReadError, ConnectionError):
                logger.info("L2 연결 끊김 감지")
                return

            tc_code = tc_bytes.decode("ascii", errors="replace")

            total_len = TC_LENGTHS.get(tc_code)
            if total_len is None:
                logger.warning(f"Unknown TC code: {tc_code}")
                continue

            try:
                remaining = await self.reader.readexactly(total_len - 4)
            except (asyncio.IncompleteReadError, ConnectionError):
                logger.info("L2 연결 끊김 (수신 중)")
                return

            full_msg = tc_bytes.decode("ascii") + remaining.decode("ascii", errors="replace")
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

        self.data_store.add_packet_log("RX", tc_code, raw, parsed_data)
        await self.ws_manager.broadcast("packet_log", {
            "direction": "RX", "tc": tc_code, "raw": raw,
            "parsed": parsed_data, "timestamp": now_str,
        })

        if tc_code == "1001":
            await self._handle_setup(raw, parsed_data)
        elif tc_code == "1002":
            await self._handle_material(raw, parsed_data)
        elif tc_code == "1010":
            await self._handle_result_change(raw, parsed_data)
        elif tc_code == "1099":
            await self._handle_alive_rx(raw, parsed_data)
        else:
            logger.info(f"RX TC={tc_code} ({len(raw)}B)")

    async def _handle_setup(self, raw: str, parsed: dict):
        """TC 1001 생산정보 수신 (L2→SPL)"""
        try:
            obj = TC1001_Setup.parse(raw)
            self.data_store.current_setup = obj
            await self.ws_manager.broadcast("setup_received", parsed)
            logger.info(f"RX TC=1001 dims={obj.dims_name} grade={obj.mat_grade}")
        except Exception as e:
            logger.error(f"Handle setup error: {e}")

    async def _handle_material(self, raw: str, parsed: dict):
        """TC 1002 소재정보 수신 (L2→SPL) → 자동 권취 트리거"""
        try:
            obj = TC1002_Material.parse(raw)
            self.data_store.current_material = obj
            self.data_store.update_coil_from_material(obj)

            await self.ws_manager.broadcast("material_received", parsed)
            logger.info(f"RX TC=1002 bundle={obj.bundle_no} line={obj.line_no}")

            # 자동 권취가 활성화되어 있으면 시작
            if self.data_store.auto_winding_enabled:
                await self.start_auto_winding(obj)
        except Exception as e:
            logger.error(f"Handle material error: {e}")

    async def _handle_result_change(self, raw: str, parsed: dict):
        """TC 1010 판정결과 변경 수신 (L2→SPL)"""
        try:
            obj = TC1010_ResultChange.parse(raw)
            self.data_store.current_result_change = obj
            await self.ws_manager.broadcast("result_change_received", parsed)
            logger.info(f"RX TC=1010 bundle={obj.bundle_no}")
        except Exception as e:
            logger.error(f"Handle result change error: {e}")

    async def _handle_alive_rx(self, raw: str, parsed: dict):
        """TC 1099 L2 Alive 수신"""
        try:
            obj = TC1099_Alive.parse(raw)
            self._last_alive_rx = asyncio.get_event_loop().time()
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            self.data_store.alive_count_rx = int(obj.count)
            self.data_store.last_alive_rx_time = now_str

            if self.data_store.connection_state != ConnectionState.ALIVE_OK:
                self.data_store.connection_state = ConnectionState.ALIVE_OK
                await self.ws_manager.broadcast("connection_changed", {
                    "state": ConnectionState.ALIVE_OK.value,
                    "timestamp": now_str,
                })

            await self.ws_manager.broadcast("alive_received", {
                "direction": "RX",
                "count": obj.count,
                "timestamp": now_str,
            })
            logger.debug(f"RX TC=1099 cnt={obj.count}")
        except Exception as e:
            logger.error(f"Handle alive RX error: {e}")

    async def _alive_send_loop(self):
        """30초 주기 TC 1199 Alive 발신"""
        try:
            while self._running and self.writer:
                await asyncio.sleep(30)
                if not self.writer:
                    break
                self.alive_counter = (self.alive_counter + 1) % 10000
                pkt = TC1199_Alive(
                    count=self.alive_counter,
                    work_a=self.data_store.work_a,
                    work_b=self.data_store.work_b,
                )
                await self.send_packet(pkt.build(), "1199")
                self.data_store.alive_count_tx = self.alive_counter
        except asyncio.CancelledError:
            pass

    async def _alive_watchdog(self):
        """L2 Alive(1099) 수신 감시: 90초 타임아웃"""
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
                        logger.warning("L2 Alive timeout (>90s)")
        except asyncio.CancelledError:
            pass

    async def send_packet(self, raw: str, tc_code: str = None):
        """TCP로 전문 전송"""
        if not self.writer:
            logger.warning("Cannot send: L2 미접속")
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

    async def send_winding_status(self, bundle_no, mtrl_no, line_no, layer_count, layers):
        """TC 1101 권취상태 전송"""
        pkt = TC1101_WindingStatus(
            bundle_no=bundle_no,
            mtrl_no=mtrl_no,
            line_no=line_no,
            layer_count=layer_count,
            layers=layers,
        )
        raw = pkt.build()
        success = await self.send_packet(raw, "1101")

        if success:
            self.data_store.update_winding(bundle_no, mtrl_no, line_no, layer_count, layers)
            await self.ws_manager.broadcast("winding_status", {
                "bundle_no": bundle_no,
                "mtrl_no": mtrl_no,
                "line_no": line_no,
                "layer_count": layer_count,
                "layers": [
                    {"index": i + 1, "status": layers[i]}
                    for i in range(25)
                ],
            })
        return success

    async def start_auto_winding(self, material=None):
        """자동 권취 시뮬레이션 시작"""
        if self._auto_winding_task and not self._auto_winding_task.done():
            self._auto_winding_task.cancel()

        mat = material or self.data_store.current_material
        if not mat:
            logger.warning("No material info for auto winding")
            return False

        self._winding_layers = []
        self._auto_winding_task = asyncio.create_task(self._auto_winding_loop(mat))
        await self.ws_manager.broadcast("auto_winding_changed", {"active": True})
        return True

    async def stop_auto_winding(self):
        """자동 권취 중지"""
        if self._auto_winding_task:
            self._auto_winding_task.cancel()
            self._auto_winding_task = None
        await self.ws_manager.broadcast("auto_winding_changed", {"active": False})
        return True

    @property
    def auto_winding_active(self) -> bool:
        return self._auto_winding_task is not None and not self._auto_winding_task.done()

    async def _auto_winding_loop(self, material):
        """자동 권취 시뮬레이션 루프"""
        status_weights = {"N": 80, "T": 10, "H": 5, "U": 5}
        population = list(status_weights.keys())
        weights = list(status_weights.values())

        self._winding_layers = []
        logger.info(f"[WINDING] Start: bundle={material.bundle_no}")

        try:
            for i in range(25):
                status = random.choices(population, weights=weights, k=1)[0]
                self._winding_layers.append(status)

                full_layers = self._winding_layers + ["N"] * (25 - len(self._winding_layers))

                await self.send_winding_status(
                    bundle_no=material.bundle_no,
                    mtrl_no=material.mtrl_no,
                    line_no=material.line_no,
                    layer_count=len(self._winding_layers),
                    layers=full_layers,
                )

                logger.info(f"[WINDING] Layer {i+1}/25: {status}")

                if i < 24:
                    delay = random.uniform(*self._winding_interval)
                    await asyncio.sleep(delay)

            logger.info("[WINDING] Complete: 25 layers")
        except asyncio.CancelledError:
            logger.info("[WINDING] Cancelled")

    async def _on_disconnected(self):
        """L2 연결 종료 처리"""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.data_store.connection_state = ConnectionState.DISCONNECTED
        self.data_store.l2_connected_since = None
        self.writer = None
        self.reader = None

        for task in [self._alive_task, self._alive_watchdog_task]:
            if task:
                task.cancel()
        self._alive_task = None
        self._alive_watchdog_task = None

        await self.ws_manager.broadcast("connection_changed", {
            "state": ConnectionState.DISCONNECTED.value,
            "timestamp": now_str,
        })
        logger.info("L2 연결 끊김")

    @staticmethod
    def _obj_to_dict(obj) -> dict:
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
