# Claude Code Prompt: Backend Agent

> **이 프롬프트를 Claude Code에 입력하여 Backend Agent를 구현하시오.**  
> **반드시 `PRD_LV2_SYSTEM.md`를 먼저 읽은 후 작업을 시작할 것.**

---

## 역할

너는 동국제강 CS공장 권취상태 모니터링 시스템의 **Backend Agent** 개발자다.  
L2(Level 2) TCP Server와 REST/WebSocket API Gateway를 구현해야 한다.

## 작업 디렉토리

`D:\DATA\python\LLM_LV2_TEST\backend\`

## 사전 조건

1. 먼저 프로젝트 루트의 `PRD_LV2_SYSTEM.md`를 읽어라. 프로토콜 명세(바이트 오프셋, 패딩 규칙)가 거기에 있다.
2. 기존 코드 `LLM_lv2_test.py`를 참고하되, 이건 PyQt6 테스트 클라이언트이므로 구조를 그대로 따르지 마라.

## 구현 요구사항

### 1. 프로토콜 모듈 (`protocol.py`)

모든 전문(TC 1001, 1002, 1010, 1099, 1101, 1199)에 대해 **빌드(build)**와 **파싱(parse)** 함수를 구현하라.

**핵심 규칙**:

```
[절대 규칙] 패킷의 총 바이트 길이가 명세와 1바이트라도 다르면 즉시 에러를 발생시켜라.
[절대 규칙] 파싱 시 단순히 .strip()으로 끝내지 마라.
           파싱 후에도 원본 raw 문자열의 각 필드 경계가 정확한지 검증하라.
[절대 규칙] spare 필드는 반드시 해당 길이만큼 스페이스(' ')로 채워라. 빈 문자열이 아니다.
[절대 규칙] 숫자형 필드(cCount, speed, temp 등)는 좌측 '0' 패딩이다.
[절대 규칙] 문자열 필드(bundle, mtrl 등)는 우측 스페이스 패딩이다.
[절대 규칙] cTcLength 필드에는 전문의 실제 총 바이트 길이를 6자리 좌측 제로패딩으로 넣어라.
```

각 TC에 대해 다음 구조를 따라라:

```python
@dataclass
class TC1001_Setup:
    """생산정보 SETUP — TC 1001, Total 128 bytes"""
    TC = "1001"
    TOTAL_LEN = 128
    
    # fields...
    
    def build(self) -> str:
        """전문 빌드. 반드시 len(result) == TOTAL_LEN 검증."""
        ...
        assert len(msg) == self.TOTAL_LEN
        return msg
    
    @classmethod
    def parse(cls, raw: str) -> "TC1001_Setup":
        """전문 파싱. raw 길이 검증 후 각 필드 추출."""
        assert len(raw) == cls.TOTAL_LEN
        assert raw[0:4] == cls.TC
        # 필드별 offset 슬라이싱...
        return cls(...)
    
    @staticmethod
    def validate_padding(raw: str) -> list[str]:
        """패딩 검증. 오류가 있으면 오류 메시지 리스트 반환."""
        errors = []
        # spare 필드 전체 스페이스 확인
        # 숫자 필드 좌측 제로 확인
        # 문자열 필드 우측 스페이스 확인
        return errors
```

### 2. TCP Server (`tcp_server.py`)

```python
# asyncio 기반 TCP Server
# - 포트: 12147 (설정 가능)
# - SPL 클라이언트 1개 연결 수락 (동시 다중 연결은 불필요)
# - 수신 데이터를 TC 코드 기준으로 라우팅
# - 수신 버퍼 관리: TCP는 스트림이므로, 고정길이 전문을 정확히 잘라내야 함

# [중요] 수신 버퍼 처리 방법:
# 1. 최소 4바이트(TC코드) 읽기
# 2. TC코드로 해당 전문의 총 길이 결정
# 3. 해당 길이만큼 정확히 읽기
# 4. 파싱 후 이벤트 발행
#
# TC별 총 길이 매핑:
#   "1101" -> 72
#   "1199" -> 52
#
# 주의: L2 서버가 수신하는 전문은 SPL→L2 방향인 1101, 1199 뿐이다.
```

**Alive 관리**:
- 30초 주기로 TC 1099 발신
- SPL의 TC 1199 수신 감시: 90초(3회 연속) 미수신 시 연결 끊김으로 판단
- Alive 카운트: 0000 ~ 9999, 초과 시 0000 리셋

**연결 상태 관리**:
```python
class ConnectionState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTED = "connected"
    ALIVE_OK = "alive_ok"         # Alive 정상 수신 중
    ALIVE_TIMEOUT = "alive_timeout"  # Alive 타임아웃
```

### 3. FastAPI REST API (`api_routes.py`)

```python
# POST /api/setup
# Body: { dims_name, spec_cd, mat_grade, qtb_speed, spl_a_speed, spl_b_speed }
# → TC 1001 빌드 → TCP로 SPL에 전송
# Response: { success, packet_hex, timestamp }

# POST /api/material  
# Body: { bundle_no, mtrl_no, heat_no, spec_cd, mat_grade, dims_name, 
#         line_no, qtb_speed, spl_a_speed, spl_b_speed, qtb_temp }
# → TC 1002 빌드 → TCP로 SPL에 전송

# POST /api/result-change
# Body: { bundle_no, mtrl_no, line_no, filenames: string[10] }
# → TC 1010 빌드 → TCP로 SPL에 전송

# GET /api/status
# Response: { connection_state, alive_count, last_alive_time,
#             work_a, work_b, spl_connected_since }

# GET /api/coils
# Response: { coils: [{ bundle_no, mtrl_no, line_no, 
#             layers: [{index, status, updated_at}], setup_info, material_info }] }

# GET /api/logs?limit=100&tc_filter=1101
# Response: { logs: [{ timestamp, direction, tc, raw_ascii, parsed }] }
```

### 4. WebSocket (`ws_manager.py`)

```python
# ws://localhost:8080/ws

# 프론트엔드 연결 시 현재 상태 전체를 push
# 이후 이벤트 발생 시마다 push:

# 이벤트 타입:
# { type: "connection_changed", data: { state, timestamp } }
# { type: "alive_received", data: { count, work_a, work_b, timestamp } }
# { type: "winding_status", data: { bundle_no, mtrl_no, line_no, layer_count, layers: [...] } }
# { type: "packet_log", data: { direction, tc, raw, parsed, timestamp } }
```

### 5. 데이터 저장 (`data_store.py`)

인메모리 dict 기반. 서버 재시작 시 초기화 OK.

```python
class DataStore:
    current_setup: Optional[TC1001_Setup]     # 현재 생산정보
    current_material: Optional[TC1002_Material]  # 현재 소재정보
    coils: dict[str, CoilData]                # bundle_no → 코일 데이터
    connection_state: ConnectionState
    alive_history: deque[AliveRecord]         # 최근 100개
    packet_logs: deque[PacketLog]             # 최근 1000개
```

### 6. 엔트리포인트 (`main.py`)

```python
# uvicorn 기반
# TCP Server와 FastAPI를 동일 이벤트 루프에서 실행
# 
# 시작 시:
# 1. TCP Server 시작 (port 12147)
# 2. FastAPI 시작 (port 8080)
# 3. 콘솔에 상태 출력
#
# Graceful shutdown 처리
```

## CORS 설정

프론트엔드(보통 별도 포트)에서 접근 가능하도록 CORS 허용:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## 실행 방법

```bash
cd D:\DATA\python\LLM_LV2_TEST\backend
pip install fastapi uvicorn websockets
python main.py
# → TCP Server listening on 0.0.0.0:12147
# → API Server running on http://0.0.0.0:8080
```

## 테스트 호환성

- tests/ 디렉토리에서 `from backend.protocol import *` 로 임포트 가능하도록 `__init__.py` 배치
- protocol.py는 spl_simulator에서도 사용하므로 import 경로 고려

## 주의사항

1. **TCP 스트림 파싱**: TCP는 메시지 경계가 없다. 바이트 스트림에서 정확히 전문 단위로 잘라내는 버퍼 로직이 필수.
2. **패딩 정확성**: SPL 측 개발자가 스페이스 패딩으로 길이를 맞추는 것을 선호한다. 빌드 시 패딩이 1바이트라도 틀리면 SPL이 파싱 실패한다.
3. **스펙 문서 오류**: PRD 섹션 9에 정리된 cTcLength 값 오류를 반드시 확인하고, 올바른 값(실제 총 길이)을 사용하라.
4. **동시성**: FastAPI(REST/WS)와 TCP Server가 같은 asyncio 루프에서 돌아야 한다. 스레드 분리는 비추.
