"""자동 권취 시뮬레이션 엔진

소재정보(1002) 수신 후 자동으로 권취를 시뮬레이션.
Layer 1~25까지 단계적으로 추가하며 1101 전문 발신.
"""

import random
import asyncio
import logging

logger = logging.getLogger(__name__)


class AutoWindingEngine:
    def __init__(
        self,
        simulator,
        material,
        interval_range: tuple = (2.0, 5.0),
        max_layers: int = 25,
        status_weights: dict = None,
    ):
        self.simulator = simulator
        self.material = material
        self.interval_range = interval_range
        self.max_layers = max_layers
        self.status_weights = status_weights or {
            "N": 80, "T": 10, "H": 5, "U": 5
        }
        self.layers: list = []
        self.cancelled = False

    def cancel(self):
        self.cancelled = True

    def _random_status(self) -> str:
        population = list(self.status_weights.keys())
        weights = list(self.status_weights.values())
        return random.choices(population, weights=weights, k=1)[0]

    async def run(self):
        logger.info(f"[WINDING] Start: bundle={self.material.bundle_no}")
        print(f"\n[WINDING] 시뮬레이션 시작: 번들={self.material.bundle_no}")

        for i in range(self.max_layers):
            if self.cancelled:
                print("[WINDING] 취소됨")
                return

            status = self._random_status()
            self.layers.append(status)

            # 25개 슬롯으로 확장 (빈 자리는 "N" 패딩)
            full_layers = self.layers + ["N"] * (25 - len(self.layers))

            await self.simulator.send_winding_status(
                bundle_no=self.material.bundle_no,
                mtrl_no=self.material.mtrl_no,
                line_no=self.material.line_no,
                layer_count=len(self.layers),
                layers=full_layers,
            )

            status_str = "/".join(self.layers)
            print(f"[WINDING] Layer {i+1:2d}/25: {status}  ({status_str})")

            if i < self.max_layers - 1:
                delay = random.uniform(*self.interval_range)
                await asyncio.sleep(delay)

        print(f"[WINDING] 시뮬레이션 완료: {len(self.layers)} layers")
        logger.info(f"[WINDING] Complete: {len(self.layers)} layers")
