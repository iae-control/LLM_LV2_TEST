# LV2 권취상태 모니터링 시스템

동국제강 CS공장 SPL ↔ Level2 TCP/IP 통신 기반 권취(Winding) 상태 모니터링 시스템.

## 아키텍처

```
┌──────────────┐     TCP 12147     ┌──────────────┐     WS/REST 8080    ┌──────────────┐
│  SPL 장비    │ ◄──────────────► │  L2 Backend  │ ◄──────────────────► │  Frontend    │
│  (시뮬레이터) │   고정길이 전문    │  (FastAPI)   │   JSON WebSocket    │  (React)     │
└──────────────┘                  └──────────────┘                     └──────────────┘
```

**통신 프로토콜** — ASCII 고정길이 전문 6종:

| TC코드 | 방향 | 설명 | 길이(B) |
|--------|------|------|---------|
| 1001 | L2→SPL | 생산정보 셋업 | 128 |
| 1002 | L2→SPL | 소재정보 | 256 |
| 1010 | L2→SPL | 판정결과 변경 | 576 |
| 1099 | L2→SPL | Alive | 64 |
| 1101 | SPL→L2 | 권취상태 | 72 |
| 1199 | SPL→L2 | Alive | 52 |

## 프로젝트 구조

```
LLM_LV2_TEST/
├── backend/              # L2 서버 (FastAPI + asyncio TCP)
│   ├── protocol.py       # 전문 빌드/파싱 (공유 모듈)
│   ├── tcp_server.py     # TCP 서버 (포트 12147)
│   ├── api_routes.py     # REST API + WebSocket
│   ├── data_store.py     # 인메모리 데이터 저장소
│   ├── ws_manager.py     # WebSocket 브로드캐스트
│   ├── main.py           # 엔트리포인트
│   └── requirements.txt
├── frontend/
│   └── index.html        # SCADA 스타일 대시보드 (CDN React)
├── spl_simulator/        # 가상 SPL 클라이언트
│   ├── simulator.py      # TCP 클라이언트 + 수신 루프
│   ├── auto_winding.py   # 자동 권취 시뮬레이션 엔진
│   └── cli.py            # CLI 메뉴 인터페이스
├── tests/                # pytest 테스트 (141건)
│   ├── conftest.py       # 공통 fixture
│   ├── test_padding.py   # 패딩 검증 (61건)
│   ├── test_protocol_build.py
│   ├── test_protocol_parse.py
│   ├── test_roundtrip.py
│   └── test_scenario.py  # TCP 통합 테스트
├── doc/                  # 설계 문서 + 스펙
├── legacy/               # 레거시 참조 코드
└── run_all.bat           # 원클릭 실행 (Windows)
```

## 설치 및 실행

### 요구사항

- Python 3.10+
- pip

### 설치

```bash
git clone https://github.com/<your-username>/LLM_LV2_TEST.git
cd LLM_LV2_TEST
pip install -r backend/requirements.txt
pip install pytest pytest-asyncio
```

### 실행

**방법 1: 일괄 실행 (Windows)**

```bash
run_all.bat
```

**방법 2: 수동 실행**

```bash
# 터미널 1 — Backend
python backend/main.py
# → TCP: 0.0.0.0:12147 / REST+WS: 0.0.0.0:8080

# 터미널 2 — SPL 시뮬레이터
python -m spl_simulator.cli --host 127.0.0.1 --port 12147

# 터미널 3 — Frontend
# frontend/index.html 을 브라우저에서 직접 열기
```

### 테스트

```bash
pytest tests/ -v
# 141 passed
```

## 주요 동작 흐름

1. Backend 시작 → TCP 12147 / HTTP 8080 바인딩
2. SPL 시뮬레이터 접속 → 30초 주기 Alive(1199) 교환 시작
3. Frontend에서 소재정보(1002) 전송 → Backend → SPL
4. SPL이 자동 권취 시작 → Layer 1~25 단계별 1101 발신
5. Backend가 1101 수신 → WebSocket으로 Frontend 실시간 브로드캐스트
6. Frontend 5x5 그리드에 N/T/H/U 상태 실시간 표시

## 기술 스택

| 구성요소 | 기술 |
|---------|------|
| Backend | Python 3.10+, FastAPI, asyncio, uvicorn |
| Frontend | React 18 (CDN), IBM Plex Sans, SCADA dark theme |
| Protocol | ASCII 고정길이 전문, dataclass 기반 빌드/파싱 |
| Test | pytest, pytest-asyncio (141 tests) |
