# SPL Winding Status Monitor

동국제강 CS공장 SPL ↔ Level2 TCP/IP 통신 기반 권취(Winding) 상태 모니터링 시스템.

## 아키텍처

```
┌──────────────┐     TCP 12147     ┌──────────────┐     WS/REST 8080    ┌──────────────┐
│  L2 Server   │ ◄──────────────► │  SPL Client  │ ◄──────────────────► │  Frontend    │
│ (130.1.1.30) │   고정길이 전문    │  (FastAPI)   │   JSON WebSocket    │  (React)     │
└──────────────┘                  └──────┬───────┘                     └──────────────┘
                                        │ FTP (seed.jpg)
                                        ▼
                                  ┌──────────────┐
                                  │  FTP Server  │
                                  │  /RECV/      │
                                  └──────────────┘
```

- **SPL Client** (Backend) → L2 서버에 TCP 클라이언트로 접속
- **L2 Server** → 생산정보(1001), 소재정보(1002), 판정변경(1010), Alive(1099) 발신
- **SPL Client** → 권취상태(1101), Alive(1199) 발신 + FTP 이미지 업로드

### 통신 프로토콜 — ASCII 고정길이 전문 6종

| TC코드 | 방향 | 설명 | 길이(B) |
|--------|------|------|---------|
| 1001 | L2→SPL | 생산정보 셋업 | 128 |
| 1002 | L2→SPL | 소재정보 | 256 |
| 1010 | L2↔SPL | 판정결과 변경 | 576 |
| 1099 | L2→SPL | Alive | 64 |
| 1101 | SPL→L2 | 권취상태 (25레이어) | 72 |
| 1199 | SPL→L2 | Alive | 52 |

## 프로젝트 구조

```
LLM_LV2_TEST/
├── backend/              # SPL TCP Client + FastAPI
│   ├── main.py           # 엔트리포인트 (CLI 인자 처리)
│   ├── tcp_client.py     # L2 접속 TCP Client + 자동권취 + FTP 업로드
│   ├── protocol.py       # 전문 빌드/파싱 (6종 TC)
│   ├── api_routes.py     # REST API + WebSocket
│   ├── data_store.py     # 인메모리 데이터 저장소
│   ├── ws_manager.py     # WebSocket 브로드캐스트
│   └── requirements.txt
├── frontend/
│   └── index.html        # SCADA 스타일 대시보드 (CDN React)
├── spl_simulator/        # 가상 SPL 클라이언트 (개발/테스트용)
│   ├── simulator.py      # TCP 클라이언트 + 수신 루프
│   ├── auto_winding.py   # 자동 권취 엔진 (단일패킷 전송)
│   └── cli.py            # CLI 메뉴 인터페이스
├── tests/                # pytest 테스트 (141건)
│   ├── conftest.py
│   ├── test_padding.py
│   ├── test_protocol_build.py
│   ├── test_protocol_parse.py
│   ├── test_roundtrip.py
│   └── test_scenario.py
├── doc/                  # 설계 문서 + 스펙
├── CHANGELOG.md          # 릴리즈노트
└── run_all.bat           # 원클릭 실행 (Windows)
```

## 설치 및 실행

### 요구사항

- Python 3.10+
- pip

### 설치

```bash
git clone https://github.com/iae-control/LLM_LV2_TEST.git
cd LLM_LV2_TEST
pip install -r backend/requirements.txt
pip install pytest pytest-asyncio
```

### 실행

```bash
python -m backend.main \
  --l2-host 130.1.1.30 \
  --l2-port 12147 \
  --image-dir D:\DATA \
  --ftp-host 130.1.1.30
```

| 인자 | 기본값 | 설명 |
|------|--------|------|
| `--l2-host` | 127.0.0.1 | L2 서버 IP |
| `--l2-port` | 12147 | L2 서버 PORT |
| `--api-port` | 8080 | REST/WS API PORT |
| `--image-dir` | (없음) | 이미지 디렉토리 (seed.jpg 위치) |
| `--ftp-host` | 130.1.1.30 | FTP 서버 IP |
| `--ftp-user` | spl_ftp | FTP 사용자 ID |
| `--ftp-pass` | !spl_ftP | FTP 비밀번호 |
| `--ftp-dir` | RECV | FTP 업로드 폴더 |

### 테스트

```bash
pytest tests/ -v
# 141 passed
```

## 주요 동작 흐름

1. Backend 시작 → L2 서버(130.1.1.30:12147)에 TCP 클라이언트로 접속
2. 30초 주기 Alive(1199) 발신, L2로부터 Alive(1099) 수신
3. L2로부터 생산정보(1001), 소재정보(1002) 수신 → 파싱 → Frontend 브로드캐스트
4. 소재정보(1002) 수신 시 자동 권취 트리거 (활성화된 경우)
5. 권취상태(1101) 전송: 25개 레이어 단일 패킷 + seed.jpg FTP 업로드 (25개 파일)
6. 판정결과 변경(1010) 수신 → 이미지 파일 리네임
7. Frontend 대시보드: 5×5 그리드에 N/T/H/U 상태 실시간 표시

### FTP 업로드 흐름

```
1101 전송 시 → seed.jpg 복사/리네임 → FTP RECV 폴더 업로드
파일명: {날짜}_{번들번호}_{강편번호}_{라인}_L{레이어}__{판정}.jpg
예시: 20260304165837_S79233B027_S79233052_B_L01_N.jpg
```

- 임시 디렉토리에 25개 파일 생성 후 FTP 업로드 (파일 잠금 방지)
- 업로드 실패 시 최대 3회 재시도 + FTP 재접속
- STOR 후 SIZE 명령으로 서버 파일 존재 검증

## 기술 스택

| 구성요소 | 기술 |
|---------|------|
| Backend | Python 3.10+, FastAPI, asyncio, uvicorn |
| Frontend | React 18 (CDN), IBM Plex Sans, SCADA dark theme |
| Protocol | ASCII 고정길이 전문, dataclass 기반 빌드/파싱 |
| FTP | ftplib, run_in_executor (비동기 래핑) |
| Test | pytest, pytest-asyncio (141 tests) |
