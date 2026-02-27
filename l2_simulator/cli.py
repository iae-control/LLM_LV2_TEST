"""L2 시뮬레이터 CLI — 메뉴 기반 인터페이스"""

import asyncio
import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from l2_simulator.server import L2Simulator

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")


async def main():
    sim = L2Simulator(host="0.0.0.0", port=12147)
    await sim.start()

    print("\n" + "=" * 50)
    print("  L2 Simulator (가상 L2 TCP Server)")
    print("  SPL 클라이언트가 접속하면 통신 시작")
    print("=" * 50)

    while True:
        print("\n--- L2 Simulator Menu ---")
        print("1. 생산정보 전송 (TC 1001)")
        print("2. 소재정보 전송 (TC 1002)")
        print("3. 판정결과 변경 전송 (TC 1010)")
        print("4. 상태 확인")
        print("5. 수신 로그 보기")
        print("q. 종료")

        try:
            choice = await asyncio.get_event_loop().run_in_executor(None, lambda: input("\n선택> ").strip())
        except (EOFError, KeyboardInterrupt):
            break

        if choice == "1":
            if not sim.connected:
                print("[!] SPL 클라이언트가 접속되지 않았습니다.")
                continue
            await sim.send_setup()

        elif choice == "2":
            if not sim.connected:
                print("[!] SPL 클라이언트가 접속되지 않았습니다.")
                continue
            await sim.send_material()

        elif choice == "3":
            if not sim.connected:
                print("[!] SPL 클라이언트가 접속되지 않았습니다.")
                continue
            fns = ["20260227_C600CZ_S78588B031_1_N.jpg"]
            await sim.send_result_change(filenames=fns)

        elif choice == "4":
            state = "접속" if sim.connected else "미접속"
            print(f"  SPL 접속상태: {state}")
            print(f"  Alive 카운트: {sim.alive_counter}")
            print(f"  수신 로그: {len(sim._rx_log)}건")

        elif choice == "5":
            if not sim._rx_log:
                print("  (수신 로그 없음)")
            else:
                for tc, raw in sim._rx_log[-10:]:
                    print(f"  TC={tc} ({len(raw)}B)")

        elif choice.lower() == "q":
            break

    await sim.stop()
    print("[L2] 종료")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
