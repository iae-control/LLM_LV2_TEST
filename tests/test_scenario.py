"""통합 시나리오 테스트 — TCP 연결 기반"""

import sys, os
import asyncio
import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.protocol import (
    TC_LENGTHS, TC1001_Setup, TC1002_Material, TC1010_ResultChange,
    TC1099_Alive, TC1101_WindingStatus, TC1199_Alive,
)


@pytest_asyncio.fixture
async def tcp_server():
    """테스트용 경량 TCP 서버 (고정길이 전문 파싱)"""
    received = []

    async def handler(reader, writer):
        while True:
            try:
                tc_bytes = await reader.readexactly(4)
            except (asyncio.IncompleteReadError, ConnectionError):
                break
            tc = tc_bytes.decode("ascii")
            total = TC_LENGTHS.get(tc)
            if total is None:
                break
            try:
                rest = await reader.readexactly(total - 4)
            except (asyncio.IncompleteReadError, ConnectionError):
                break
            full = tc_bytes.decode("ascii") + rest.decode("ascii")
            received.append(full)
        writer.close()

    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    yield server, port, received
    server.close()
    await server.wait_closed()


@pytest.mark.asyncio
class TestTCPScenario:
    async def test_send_and_receive_1199(self, tcp_server):
        """1199 Alive 전문 송수신"""
        server, port, received = tcp_server
        reader, writer = await asyncio.open_connection("127.0.0.1", port)

        pkt = TC1199_Alive(count=1, work_a="01", work_b="01")
        raw = pkt.build()
        writer.write(raw.encode("ascii"))
        await writer.drain()

        await asyncio.sleep(0.1)
        assert len(received) == 1
        assert received[0][0:4] == "1199"
        assert len(received[0]) == 52

        writer.close()
        await writer.wait_closed()

    async def test_send_and_receive_1101(self, tcp_server):
        """1101 권취상태 전문 송수신"""
        server, port, received = tcp_server
        reader, writer = await asyncio.open_connection("127.0.0.1", port)

        pkt = TC1101_WindingStatus(
            bundle_no="S78588B031", mtrl_no="S78588069",
            line_no="A", layer_count=10,
            layers=["N"] * 10 + ["U"] * 15,
        )
        raw = pkt.build()
        writer.write(raw.encode("ascii"))
        await writer.drain()

        await asyncio.sleep(0.1)
        assert len(received) == 1
        assert received[0][0:4] == "1101"
        assert len(received[0]) == 72

        parsed = TC1101_WindingStatus.parse(received[0])
        assert parsed.bundle_no == "S78588B031"
        assert parsed.layer_count == 10

        writer.close()
        await writer.wait_closed()

    async def test_multiple_packets_stream(self, tcp_server):
        """여러 전문을 연속으로 보내도 정확히 파싱됨 (TCP 스트림 테스트)"""
        server, port, received = tcp_server
        reader, writer = await asyncio.open_connection("127.0.0.1", port)

        pkt1 = TC1199_Alive(count=1).build()
        pkt2 = TC1101_WindingStatus(bundle_no="TEST").build()
        pkt3 = TC1199_Alive(count=2).build()

        # 3개 전문을 한꺼번에 전송
        writer.write((pkt1 + pkt2 + pkt3).encode("ascii"))
        await writer.drain()

        await asyncio.sleep(0.2)
        assert len(received) == 3
        assert received[0][0:4] == "1199"
        assert received[1][0:4] == "1101"
        assert received[2][0:4] == "1199"

        writer.close()
        await writer.wait_closed()

    async def test_client_disconnect_detection(self, tcp_server):
        """클라이언트 연결 끊김 감지"""
        server, port, received = tcp_server
        reader, writer = await asyncio.open_connection("127.0.0.1", port)

        pkt = TC1199_Alive(count=1).build()
        writer.write(pkt.encode("ascii"))
        await writer.drain()
        await asyncio.sleep(0.1)

        writer.close()
        await writer.wait_closed()
        await asyncio.sleep(0.1)

        assert len(received) == 1
