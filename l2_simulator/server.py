"""L2 시뮬레이터 — 가상 L2 TCP Server

개발/테스트용. 실제 L2 서버를 시뮬레이션한다.
  - TCP Server로 대기 (port 12147)
  - SPL 클라이언트 접속 수락
  - Alive(1099) 30초 주기 발신
  - 1001/1002/1010 전송 기능
  - SPL로부터 1101/1199 수신 & 표시
"""

import asyncio
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.protocol import (
    TC_LENGTHS, TC_PARSERS,
    TC1001_Setup, TC1002_Material, TC1010_ResultChange,
    TC1099_Alive, TC1101_WindingStatus, TC1199_Alive,
)

logger = logging.getLogger(__name__)


class L2Simulator:
    def __init__(self, host: str = "0.0.0.0", port: int = 12147):
        self.host = host
        self.port = port
        self.reader: asyncio.StreamReader = None
        self.writer: asyncio.StreamWriter = None
        self.server: asyncio.AbstractServer = None
        self.alive_counter = 0
        self.connected = False
        self._alive_task: asyncio.Task = None
        self._receive_task: asyncio.Task = None
        self._running = False
        self._rx_log: list = []

    async def start(self):
        self.server = await asyncio.start_server(
            self._handle_client, self.host, self.port
        )
        self._running = True
        print(f"[L2] TCP Server listening on {self.host}:{self.port}")
        print("[L2] SPL 클라이언트 접속 대기중...")

    async def stop(self):
        self._running = False
        if self._alive_task:
            self._alive_task.cancel()
        if self._receive_task:
            self._receive_task.cancel()
        if self.writer:
            try:
                self.writer.close()
            except Exception:
                pass
        if self.server:
            self.server.close()

    async def _handle_client(self, reader, writer):
        peer = writer.get_extra_info("peername")
        print(f"\n[L2] SPL 클라이언트 접속: {peer}")

        if self.writer:
            try:
                self.writer.close()
            except Exception:
                pass

        self.reader = reader
        self.writer = writer
        self.connected = True

        if self._alive_task:
            self._alive_task.cancel()
        self._alive_task = asyncio.create_task(self._alive_loop())

        try:
            await self._receive_loop(reader)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[L2] 수신 오류: {e}")
        finally:
            self.connected = False
            self.writer = None
            self.reader = None
            print("[L2] SPL 클라이언트 연결 해제")

    async def _receive_loop(self, reader):
        while self._running:
            try:
                tc_bytes = await reader.readexactly(4)
            except (asyncio.IncompleteReadError, ConnectionError):
                return

            tc_code = tc_bytes.decode("ascii", errors="replace")
            total_len = TC_LENGTHS.get(tc_code)
            if total_len is None:
                print(f"[L2] Unknown TC: {tc_code}")
                continue

            try:
                remaining = await reader.readexactly(total_len - 4)
            except (asyncio.IncompleteReadError, ConnectionError):
                return

            full_msg = tc_bytes.decode("ascii") + remaining.decode("ascii", errors="replace")
            self._rx_log.append((tc_code, full_msg))
            self._handle_rx(tc_code, full_msg)

    def _handle_rx(self, tc_code, raw):
        try:
            if tc_code == "1101":
                obj = TC1101_WindingStatus.parse(raw)
                layers_str = "/".join(obj.layers[:int(obj.layer_count)])
                print(f"[RX 1101] 번들={obj.bundle_no} 라인={obj.line_no} "
                      f"Layer={obj.layer_count}/25 [{layers_str}]")
            elif tc_code == "1199":
                obj = TC1199_Alive.parse(raw)
                print(f"[RX 1199] cnt={obj.count} A={obj.work_a} B={obj.work_b}")
            else:
                print(f"[RX {tc_code}] {len(raw)}B")
        except Exception as e:
            print(f"[RX {tc_code}] 파싱 오류: {e}")

    async def _alive_loop(self):
        try:
            while self._running and self.connected:
                await asyncio.sleep(30)
                if not self.writer:
                    break
                self.alive_counter = (self.alive_counter + 1) % 10000
                pkt = TC1099_Alive(count=self.alive_counter)
                await self._send(pkt.build())
                print(f"[TX 1099] Alive cnt={self.alive_counter}")
        except asyncio.CancelledError:
            pass

    async def send_setup(self, dims_name="BL1600", spec_cd="KS SD600",
                         mat_grade="C600CZ", qtb_speed="01513",
                         spl_a_speed="01588", spl_b_speed="01588"):
        pkt = TC1001_Setup(
            dims_name=dims_name, spec_cd=spec_cd, mat_grade=mat_grade,
            qtb_speed=qtb_speed, spl_a_speed=spl_a_speed, spl_b_speed=spl_b_speed,
        )
        raw = pkt.build()
        await self._send(raw)
        print(f"[TX 1001] 제품명={dims_name} 강종={mat_grade}")

    async def send_material(self, bundle_no="S78588B031", mtrl_no="S78588069",
                            heat_no="S78588", spec_cd="KS SD600",
                            mat_grade="C600CZ", dims_name="BL1600",
                            line_no="A", qtb_speed="01513",
                            spl_a_speed="01588", spl_b_speed="01588",
                            qtb_temp="0400"):
        pkt = TC1002_Material(
            bundle_no=bundle_no, mtrl_no=mtrl_no, heat_no=heat_no,
            spec_cd=spec_cd, mat_grade=mat_grade, dims_name=dims_name,
            line_no=line_no, qtb_speed=qtb_speed,
            spl_a_speed=spl_a_speed, spl_b_speed=spl_b_speed,
            qtb_temp=qtb_temp,
        )
        raw = pkt.build()
        await self._send(raw)
        print(f"[TX 1002] 번들={bundle_no} 라인={line_no}")

    async def send_result_change(self, bundle_no="S78588B031", mtrl_no="S78588069",
                                  line_no="A", filenames=None):
        pkt = TC1010_ResultChange(
            bundle_no=bundle_no, mtrl_no=mtrl_no, line_no=line_no,
            filenames=filenames or [],
        )
        raw = pkt.build()
        await self._send(raw)
        print(f"[TX 1010] 번들={bundle_no} 라인={line_no}")

    async def _send(self, raw: str):
        if self.writer:
            try:
                self.writer.write(raw.encode("ascii"))
                await self.writer.drain()
            except Exception as e:
                print(f"[L2] 전송 오류: {e}")
