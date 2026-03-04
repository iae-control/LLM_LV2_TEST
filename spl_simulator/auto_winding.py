"""자동 권취 시뮬레이션 엔진

소재정보(1002) 수신 후 자동으로 1101 전문 발신.
25개 레이어 상태를 한 번에 전송 (단일 패킷).
"""

import asyncio
import logging

logger = logging.getLogger(__name__)


class AutoWindingEngine:
    def __init__(
        self,
        simulator,
        material,
        max_layers: int = 25,
        default_status: str = "N",
        layers: list = None,
    ):
        self.simulator = simulator
        self.material = material
        self.max_layers = max_layers
        self.default_status = default_status
        # 외부에서 지정한 레이어 상태 사용, 없으면 전부 default_status
        if layers:
            self.layers = (layers + [default_status] * max_layers)[:max_layers]
        else:
            self.layers = [default_status] * max_layers
        self.cancelled = False

    def cancel(self):
        self.cancelled = True

    async def run(self):
        """25개 레이어 상태를 한 번에 전송 (단일 1101 패킷)"""
        if self.cancelled:
            print("[WINDING] 취소됨")
            return

        logger.info(
            f"[WINDING] Send: bundle={self.material.bundle_no} "
            f"mtrl={self.material.mtrl_no} line={self.material.line_no} "
            f"layers={''.join(self.layers[:self.max_layers])}"
        )
        print(
            f"\n[WINDING] 1101 전송: 번들={self.material.bundle_no} "
            f"레이어={''.join(self.layers[:self.max_layers])}"
        )

        await self.simulator.send_winding_status(
            bundle_no=self.material.bundle_no,
            mtrl_no=self.material.mtrl_no,
            line_no=self.material.line_no,
            layer_count=self.max_layers,
            layers=self.layers,
        )

        print(f"[WINDING] 전송 완료: {self.max_layers} layers")
        logger.info(f"[WINDING] Complete: {self.max_layers} layers")
