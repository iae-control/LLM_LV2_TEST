"""SPL 시뮬레이터 — 가상 SPL TCP 클라이언트

L2 서버에 접속하여:
  - Alive(1199) 30초 주기 발신
  - L2로부터 1001, 1002, 1010, 1099 수신 & 파싱
  - 소재정보(1002) 수신 시 자동 권취 시뮬레이션 시작
"""

import asyncio
import logging
import sys
import os

# 프로젝트 루트를 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.protocol import (
    TC_LENGTHS, TC_PARSERS,
    TC1001_Setup, TC1002_Material, TC1010_ResultChange,
    TC1099_Alive, TC1101_WindingStatus, TC1199_Alive,
)
from spl_simulator.auto_winding import AutoWindingEngine

logger = logging.getLogger(__name__)

# L2 → SPL 방향 TC 코드 (시뮬레이터가 수신하는 전문)
L2_TO_SPL_TC = {"1001": 128, "1002": 256, "1010": 576, "1099": 64}


class SPLSimulator:
    def __init__(self, host: str = "127.0.0.1", port: int = 12147):
        self.host = host
        self.port = port
        self.reader: asyncio.StreamReader = None
        self.writer: asyncio.StreamWriter = None
        self.alive_counter = 0
        self.work_a = "01"
        self.work_b = "01"
        self.connected = False
        self.current_material = None
        self.winding_engine: AutoWindingEngine = None
        self._alive_task: asyncio.Task = None
        self._receive_task: asyncio.Task = None
        self._rx_log: list = []
        self._interval_range = (2.0, 5.0)

    async def connect(self):
        try:
            self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
            self.connected = True
            print(f"[SPL] L2 서버 접속 성공: {self.host}:{self.port}")
            logger.info(f"Connected to L2 at {self.host}:{self.port}")

            self._alive_task = asyncio.create_task(self._alive_loop())
            self._receive_task = asyncio.create_task(self._receive_loop())
            return True
        except Exception as e:
            print(f"[SPL] 접속 실패: {e}")
            logger.error(f"Connection failed: {e}")
            return False

    async def disconnect(self):
        self.connected = False
        if self.winding_engine:
            self.winding_engine.cancel()
            self.winding_engine = None
        if self._alive_task:
            self._alive_task.cancel()
            self._alive_task = None
        if self._receive_task:
            self._receive_task.cancel()
            self._receive_task = None
        if self.writer:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception:
                pass
            self.writer = None
            self.reader = None
        print("[SPL] 연결 해제됨")

    async def send_alive(self):
        self.alive_counter = (self.alive_counter + 1) % 10000
        pkt = TC1199_Alive(
            count=self.alive_counter,
            work_a=self.work_a,
            work_b=self.work_b,
        )
        raw = pkt.build()
        await self._send(raw)
        logger.debug(f"TX 1199 cnt={self.alive_counter}")

    async def _alive_loop(self):
        try:
            while self.connected:
                await asyncio.sleep(30)
                if self.connected and self.writer:
                    await self.send_alive()
        except asyncio.CancelledError:
            pass

    async def _receive_loop(self):
        try:
            while self.connected and self.reader:
                # 1. TC 코드 4바이트 읽기
                try:
                    tc_bytes = await self.reader.readexactly(4)
                except (asyncio.IncompleteReadError, ConnectionError):
                    print("[SPL] L2 연결 끊김 감지")
                    break

                tc_code = tc_bytes.decode("ascii", errors="replace")

                # 2. 해당 TC 총 길이
                total_len = TC_LENGTHS.get(tc_code)
                if total_len is None:
                    logger.warning(f"Unknown TC: {tc_code}")
                    continue

                # 3. 나머지 읽기
                try:
                    remaining = await self.reader.readexactly(total_len - 4)
                except (asyncio.IncompleteReadError, ConnectionError):
                    print("[SPL] L2 연결 끊김 (수신 중)")
                    break

                full_msg = tc_bytes.decode("ascii") + remaining.decode("ascii", errors="replace")
                await self._dispatch(tc_code, full_msg)
        except asyncio.CancelledError:
            pass
        finally:
            if self.connected:
                self.connected = False
                print("[SPL] 수신 루프 종료")

    async def _dispatch(self, tc_code: str, raw: str):
        self._rx_log.append((tc_code, raw))

        try:
            if tc_code == "1001":
                obj = TC1001_Setup.parse(raw)
                await self._handle_setup(obj)
            elif tc_code == "1002":
                obj = TC1002_Material.parse(raw)
                await self._handle_material(obj)
            elif tc_code == "1010":
                obj = TC1010_ResultChange.parse(raw)
                await self._handle_result_change(obj)
            elif tc_code == "1099":
                obj = TC1099_Alive.parse(raw)
                await self._handle_alive(obj)
            else:
                print(f"[SPL] RX unknown TC={tc_code} ({len(raw)}B)")
        except Exception as e:
            logger.error(f"Dispatch error TC {tc_code}: {e}")
            print(f"[SPL] 파싱 오류 TC={tc_code}: {e}")

    async def _handle_setup(self, data: TC1001_Setup):
        print(f"[RX 1001] 제품명={data.dims_name} 강종={data.mat_grade} "
              f"QTB={data.qtb_speed} SPL_A={data.spl_a_speed} SPL_B={data.spl_b_speed}")

    async def _handle_material(self, data: TC1002_Material):
        self.current_material = data
        print(f"[RX 1002] 번들={data.bundle_no} MTRL={data.mtrl_no} "
              f"라인={data.line_no} 제품명={data.dims_name}")

        # 자동 권취 시작
        if self.winding_engine:
            self.winding_engine.cancel()
        self.winding_engine = AutoWindingEngine(
            self, data, interval_range=self._interval_range
        )
        asyncio.create_task(self.winding_engine.run())

    async def _handle_result_change(self, data: TC1010_ResultChange):
        file_count = sum(1 for f in data.filenames if f.strip())
        print(f"[RX 1010] 번들={data.bundle_no} MTRL={data.mtrl_no} "
              f"라인={data.line_no} 파일수={file_count}")
        for i, fn in enumerate(data.filenames):
            if fn.strip():
                print(f"  파일{i+1}: {fn}")

    async def _handle_alive(self, data: TC1099_Alive):
        logger.debug(f"RX 1099 cnt={data.count}")

    async def send_winding_status(self, bundle_no, mtrl_no, line_no, layer_count, layers):
        pkt = TC1101_WindingStatus(
            bundle_no=bundle_no,
            mtrl_no=mtrl_no,
            line_no=line_no,
            layer_count=layer_count,
            layers=layers,
        )
        raw = pkt.build()
        await self._send(raw)

    async def _send(self, raw: str):
        if self.writer:
            try:
                self.writer.write(raw.encode("ascii"))
                await self.writer.drain()
            except Exception as e:
                logger.error(f"Send error: {e}")
                print(f"[SPL] 전송 오류: {e}")

    def set_interval(self, min_sec: float, max_sec: float):
        self._interval_range = (min_sec, max_sec)
        if self.winding_engine:
            self.winding_engine.interval_range = self._interval_range
        print(f"[SPL] 권취 간격 설정: {min_sec}~{max_sec}초")
