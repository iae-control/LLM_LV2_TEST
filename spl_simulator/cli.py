"""SPL 시뮬레이터 CLI 인터페이스

사용법: python -m spl_simulator.cli [--host HOST] [--port PORT]
"""

import asyncio
import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from spl_simulator.simulator import SPLSimulator


MENU = """
========================================
  SPL 시뮬레이터 CLI
========================================
  1. 서버 접속
  2. 서버 접속 해제
  3. Alive 상태 변경 (A/B 라인)
  4. 수동 Alive(1199) 발신
  5. 자동 권취 속도 조절
  6. 현재 상태 표시
  7. 수신 로그 표시
  0. 종료
========================================
"""


async def run_cli(host: str, port: int):
    sim = SPLSimulator(host=host, port=port)

    print(f"\nSPL 시뮬레이터 시작 (서버: {host}:{port})")
    print("1002(소재정보) 수신 시 자동으로 권취 시뮬레이션이 시작됩니다.")

    loop = asyncio.get_event_loop()

    while True:
        print(MENU)
        try:
            # 비동기 input (별도 스레드)
            choice = await loop.run_in_executor(None, lambda: input("선택> ").strip())
        except (EOFError, KeyboardInterrupt):
            break

        if choice == "1":
            if sim.connected:
                print("[!] 이미 접속 중입니다.")
            else:
                await sim.connect()

        elif choice == "2":
            if not sim.connected:
                print("[!] 접속되어 있지 않습니다.")
            else:
                await sim.disconnect()

        elif choice == "3":
            print(f"  현재: A={sim.work_a}, B={sim.work_b}")
            a = await loop.run_in_executor(
                None, lambda: input("  A라인 (01=정상, 99=비정상): ").strip()
            )
            b = await loop.run_in_executor(
                None, lambda: input("  B라인 (01=정상, 99=비정상): ").strip()
            )
            if a in ("01", "99"):
                sim.work_a = a
            if b in ("01", "99"):
                sim.work_b = b
            print(f"  변경됨: A={sim.work_a}, B={sim.work_b}")

        elif choice == "4":
            if not sim.connected:
                print("[!] 접속되어 있지 않습니다.")
            else:
                await sim.send_alive()
                print(f"[TX] 1199 Alive 발신 (cnt={sim.alive_counter})")

        elif choice == "5":
            min_s = await loop.run_in_executor(
                None, lambda: input("  최소 간격(초, 기본 2.0): ").strip()
            )
            max_s = await loop.run_in_executor(
                None, lambda: input("  최대 간격(초, 기본 5.0): ").strip()
            )
            try:
                mn = float(min_s) if min_s else 2.0
                mx = float(max_s) if max_s else 5.0
                sim.set_interval(mn, mx)
            except ValueError:
                print("[!] 숫자를 입력하세요.")

        elif choice == "6":
            print(f"\n  접속 상태: {'접속중' if sim.connected else '미접속'}")
            print(f"  서버: {sim.host}:{sim.port}")
            print(f"  Alive 카운터: {sim.alive_counter}")
            print(f"  A라인: {sim.work_a}, B라인: {sim.work_b}")
            if sim.current_material:
                m = sim.current_material
                print(f"  현재 소재: 번들={m.bundle_no} MTRL={m.mtrl_no} 라인={m.line_no}")
            if sim.winding_engine:
                we = sim.winding_engine
                print(f"  권취 진행: {len(we.layers)}/{we.max_layers} layers")
                print(f"  권취 간격: {we.interval_range[0]}~{we.interval_range[1]}초")

        elif choice == "7":
            if not sim._rx_log:
                print("  수신 로그 없음")
            else:
                print(f"\n  최근 수신 {min(20, len(sim._rx_log))}건:")
                for tc, raw in sim._rx_log[-20:]:
                    print(f"    TC={tc} ({len(raw)}B)")

        elif choice == "0":
            if sim.connected:
                await sim.disconnect()
            print("종료합니다.")
            break

        else:
            print("[!] 잘못된 선택입니다.")


def main():
    parser = argparse.ArgumentParser(description="SPL Simulator CLI")
    parser.add_argument("--host", default="127.0.0.1", help="L2 server host")
    parser.add_argument("--port", type=int, default=12147, help="L2 server port")
    args = parser.parse_args()

    try:
        asyncio.run(run_cli(args.host, args.port))
    except KeyboardInterrupt:
        print("\n종료됨")


if __name__ == "__main__":
    main()
