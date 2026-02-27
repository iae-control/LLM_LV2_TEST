# PRD: 동국제강 CS공장 권취상태 모니터링 LV2 시스템

> **Project**: Dongkuk Steel CS Mill Winding Status Monitoring  
> **Version**: 1.0  
> **Date**: 2026-02-27  
> **Author**: IAE (고등기술연구원)

---

## 1. 개요

동국제강 CS공장의 권취상태 모니터링 시스템(SPL)과 Level2 서버 간의 TCP/IP 소켓 통신을 구현한다.  
Level2는 TCP Server, SPL은 TCP Client 역할이다.

실제 SPL 장비가 연결되지 않은 개발 환경이므로, **가상 SPL 시뮬레이터**를 별도로 구현하여 테스트한다.

### 1.1 시스템 구성 (3-Agent Architecture)

| Agent | 역할 | 기술 스택 |
|-------|------|----------|
| **Backend Agent** | L2 TCP Server + REST/WebSocket API | Python asyncio, FastAPI, WebSocket |
| **Frontend Agent** | 산업용 모니터링 대시보드 | React (JSX), Industrial Design |
| **Test Agent** | SPL 시뮬레이터 + 자동화 테스트 | Python asyncio TCP Client, pytest |

### 1.2 네트워크 구성 (원본 스펙)

| 구분 | 역할 | IP | PORT |
|------|------|-----|------|
| LEVEL 2 → SPL | Server | 130.1.1.30 | 12147 |
| SPL → LEVEL 2 | Client | 10.10.97.132 | (connects to above) |

> **개발 환경에서는** `localhost:12147` 사용

### 1.3 통신 규약

- **프로토콜**: 1IP - 2Port TCP/IP Socket (Server/Client)
- **인코딩**: ASCII 고정길이 전문 (Fixed-length ASCII)
- **바이트 순서**: Big-endian (network byte order) 아닌 ASCII 문자열
- **패딩 규칙**:
  - **문자열(char) 필드**: 우측 스페이스(`' '`) 패딩으로 고정 길이 맞춤
  - **숫자형 필드** (count, speed, temp 등): 좌측 제로(`'0'`) 패딩
  - **spare 필드**: 전체 스페이스(`' '`) 채움
- **Alive 체크**: 30초 주기
- **카운트**: 0000 ~ 9999, 9999 초과 시 0000 리셋

---

## 2. 프로토콜 명세 (Byte-Level)

> ⚠️ **중요**: 모든 오프셋은 0-based index이다.  
> ⚠️ **패딩 검증 필수**: 파싱 시 단순히 `.strip()` 하지 말고, 패딩 문자가 올바르게 들어갔는지 검증할 것.  
> SPL 측 개발자는 **스페이스 패딩으로 길이를 맞추는 것을 선호**하므로, 빌드 시에도 반드시 정확한 길이를 보장해야 한다.

### 2.1 공통 헤더 구조 (24 bytes)

모든 전문의 첫 24바이트는 동일 구조:

| Offset | Field | Size | Type | Padding | Description |
|--------|-------|------|------|---------|-------------|
| 0-3 | cTcCode | 4 | char | 없음 | TC 코드 (e.g. "1001") |
| 4-17 | cDate | 14 | char | 없음 | 송신시간 "YYYYMMDDhhmmss" |
| 18-23 | cTcLength | 6 | char | 좌측 '0' | 전문 총 길이 (e.g. "000128") |

### 2.2 TC 1001 — 생산정보 SETUP (L2→SPL)

**총 길이: 128 bytes**

| Offset | Field | Size | Padding | Example | Description |
|--------|-------|------|---------|---------|-------------|
| 0-3 | cTcCode | 4 | - | `"1001"` | TC Code |
| 4-17 | cDate | 14 | - | `"20260227143000"` | 송신시간 |
| 18-23 | cTcLength | 6 | 좌측 '0' | `"000128"` | 전문길이 |
| 24-29 | cDIMS_NAME | 6 | 우측 ' ' | `"BL1600"` | 제품명 |
| 30-69 | cSPEC_CD | 40 | 우측 ' ' | `"KS SD600····"` | 규격약호 |
| 70-76 | cMAT_GRADE | 7 | 우측 ' ' | `"C600CZ "` | 강종 |
| 77-81 | cQTB_SPEED | 5 | 좌측 '0' | `"01513"` | QTB 선속 (×100) |
| 82-86 | cSPL_A_SPEED | 5 | 좌측 '0' | `"01588"` | SPL A 선속 (×100) |
| 87-91 | cSPL_B_SPEED | 5 | 좌측 '0' | `"01588"` | SPL B 선속 (×100) |
| 92-127 | spare | 36 | 전체 ' ' | `"····"` | 여유공간 |

**검증**: 4+14+6+6+40+7+5+5+5+36 = **128** ✓

> ⚠️ **스펙 문서 오류**: 원본 XLS의 cTcLength 필드에 `"000512"`로 기재되어 있으나, 실제 Tot는 128. `"000128"`이 올바른 값이다.

### 2.3 TC 1002 — 소재정보 (L2→SPL)

**총 길이: 256 bytes**

| Offset | Field | Size | Padding | Example | Description |
|--------|-------|------|---------|---------|-------------|
| 0-3 | cTcCode | 4 | - | `"1002"` | TC Code |
| 4-17 | cDate | 14 | - | `"20260227143000"` | 송신시간 |
| 18-23 | cTcLength | 6 | 좌측 '0' | `"000256"` | 전문길이 |
| 24-33 | cBUNDLE_NO | 10 | 우측 ' ' | `"S78588B031"` | 번들번호(코일번호) |
| 34-43 | cMTRL_NO1 | 10 | 우측 ' ' | `"S78588069 "` | 강편번호(대표) |
| 44-49 | cHEAT_NO | 6 | 우측 ' ' | `"S78588"` | HEAT 번호 |
| 50-89 | cSPEC_CD | 40 | 우측 ' ' | `"KS SD600····"` | 규격약호 |
| 90-96 | cMAT_GRADE | 7 | 우측 ' ' | `"C600CZ "` | 강종 |
| 97-102 | cDIMS_NAME | 6 | 우측 ' ' | `"BL1600"` | 제품명 |
| 103 | cLine_NO | 1 | 없음 | `"A"` | 작업 Line (A/B) |
| 104-108 | cQTB_SPEED | 5 | 좌측 '0' | `"01513"` | QTB 선속 (×100) |
| 109-113 | cSPL_A_SPEED | 5 | 좌측 '0' | `"01588"` | SPL A 선속 (×100) |
| 114-118 | cSPL_B_SPEED | 5 | 좌측 '0' | `"01588"` | SPL B 선속 (×100) |
| 119-122 | cQTB_TEMP | 4 | 좌측 '0' | `"0400"` | QTB 복열온도 |
| 123-255 | spare | 133 | 전체 ' ' | `"····"` | 여유공간 |

**검증**: 4+14+6+10+10+6+40+7+6+1+5+5+5+4+133 = **256** ✓

> ⚠️ **스펙 문서 오류**: cTcLength `"000512"` 기재 → 실제 `"000256"`

### 2.4 TC 1010 — 판정결과 변경 (L2→SPL)

**총 길이: 576 bytes**

| Offset | Field | Size | Padding | Example | Description |
|--------|-------|------|---------|---------|-------------|
| 0-3 | cTcCode | 4 | - | `"1010"` | TC Code |
| 4-17 | cDate | 14 | - | | 송신시간 |
| 18-23 | cTcLength | 6 | 좌측 '0' | `"000576"` | 전문길이 |
| 24-33 | cBUNDLE_NO | 10 | 우측 ' ' | `"S78588B031"` | 번들번호 |
| 34-43 | cMTRL_NO1 | 10 | 우측 ' ' | `"S78588069 "` | 강편번호 |
| 44 | cLine_NO | 1 | 없음 | `"A"` | 작업 Line |
| 45-94 | cSPL_STATUS_MOD1 | 50 | 우측 ' ' | `"20251230150001_C300ZZ_S73845B015_1_N.jpg···"` | 변경 이미지1 |
| 95-144 | cSPL_STATUS_MOD2 | 50 | 우측 ' ' | | 변경 이미지2 |
| 145-194 | cSPL_STATUS_MOD3 | 50 | 우측 ' ' | | 변경 이미지3 |
| 195-244 | cSPL_STATUS_MOD4 | 50 | 우측 ' ' | | 변경 이미지4 |
| 245-294 | cSPL_STATUS_MOD5 | 50 | 우측 ' ' | | 변경 이미지5 |
| 295-344 | cSPL_STATUS_MOD6 | 50 | 우측 ' ' | | 변경 이미지6 |
| 345-394 | cSPL_STATUS_MOD7 | 50 | 우측 ' ' | | 변경 이미지7 |
| 395-444 | cSPL_STATUS_MOD8 | 50 | 우측 ' ' | | 변경 이미지8 |
| 445-494 | cSPL_STATUS_MOD9 | 50 | 우측 ' ' | | 변경 이미지9 |
| 495-544 | cSPL_STATUS_MOD10 | 50 | 우측 ' ' | | 변경 이미지10 |
| 545-575 | cSpare | 31 | 전체 ' ' | | 여유공간 |

**검증**: 4+14+6+10+10+1+(50×10)+31 = 4+14+6+10+10+1+500+31 = **576** ✓

> ⚠️ **스펙 문서 오류**: cTcLength `"000512"` 기재 → 실제 `"000576"`. 기존 테스트 코드(LLM_lv2_test.py)에서도 `"000576"` 사용 중.

### 2.5 TC 1099 — Alive (L2→SPL)

**총 길이: 64 bytes**

| Offset | Field | Size | Padding | Example | Description |
|--------|-------|------|---------|---------|-------------|
| 0-3 | cTcCode | 4 | - | `"1099"` | TC Code |
| 4-17 | cDate | 14 | - | | 송신시간 |
| 18-23 | cTcLength | 6 | 좌측 '0' | `"000064"` | 전문길이 |
| 24-27 | cCount | 4 | 좌측 '0' | `"0001"` | 카운트 (0000~9999, 리셋) |
| 28-63 | cSpare | 36 | 전체 ' ' | | 여유공간 |

**검증**: 4+14+6+4+36 = **64** ✓

> ⚠️ **스펙 문서 오류**: cTcLength `"000050"` 기재, size `64`로 기재. 실제 계산값은 64이므로 `"000064"`가 올바른 값이다.

### 2.6 TC 1101 — 권취상태 (SPL→L2)

**총 길이: 72 bytes**

| Offset | Field | Size | Padding | Example | Description |
|--------|-------|------|---------|---------|-------------|
| 0-3 | cTcCode | 4 | - | `"1101"` | TC Code |
| 4-17 | cDate | 14 | - | | 송신시간 |
| 18-23 | cTcLength | 6 | 좌측 '0' | `"000072"` | 전문길이 |
| 24-33 | cBUNDLE_NO | 10 | 우측 ' ' | `"S78588B031"` | 번들번호 |
| 34-43 | cMTRL_NO1 | 10 | 우측 ' ' | `"S78588069 "` | 강편번호 |
| 44 | cLine_NO | 1 | 없음 | `"A"` | 작업 Line |
| 45-46 | cSPL_LAYER_COUNT | 2 | 좌측 '0' | `"25"` | Layer Count (1~25) |
| 47 | cSPL_STATUS_LAYER1 | 1 | 없음 | `"N"` | Layer 1 상태 |
| 48 | cSPL_STATUS_LAYER2 | 1 | 없음 | `"T"` | Layer 2 상태 |
| ... | ... | 1 | 없음 | | Layer 3~24 상태 |
| 71 | cSPL_STATUS_LAYER25 | 1 | 없음 | `"N"` | Layer 25 상태 |

**Layer 상태 코드**:
- `N` = Normal (정상)
- `T` = Twist (꼬임)
- `H` = Hooking (걸림)
- `U` = Unmeasured (미측정)

**검증**: 4+14+6+10+10+1+2+25 = **72** ✓

### 2.7 TC 1199 — Alive (SPL→L2)

**총 길이: 52 bytes**

| Offset | Field | Size | Padding | Example | Description |
|--------|-------|------|---------|---------|-------------|
| 0-3 | cTcCode | 4 | - | `"1199"` | TC Code |
| 4-17 | cDate | 14 | - | | 송신시간 |
| 18-23 | cTcLength | 6 | 좌측 '0' | `"000052"` | 전문길이 |
| 24-27 | cCount | 4 | 좌측 '0' | `"0001"` | 카운트 |
| 28-29 | cWork_A | 2 | 좌측 '0' | `"01"` | A라인 가동상태 |
| 30-31 | cWork_B | 2 | 좌측 '0' | `"01"` | B라인 가동상태 |
| 32-51 | cSpare | 20 | 전체 ' ' | | 여유공간 |

**가동상태 코드**: `"01"` = 정상가동, `"99"` = 비정상

**검증**: 4+14+6+4+2+2+20 = **52** ✓

---

## 3. 통신 시퀀스

### 3.1 정상 연결

```
[L2 Server]                     [SPL Client]
    |          TCP Connect            |
    |<--------------------------------|
    |          Connected OK           |
    |-------------------------------->|
    |                                 |
    |--- 1001 생산정보 (SETUP) ------>|  가열로 추출 시
    |                                 |
    |--- 1002 소재정보 ------------->|  SPL 언로딩 시점
    |                                 |
    |          (권취 진행중)           |
    |<--- 1101 권취상태 -------------|  실시간 레이어별 상태
    |<--- 1101 권취상태 -------------|  (레이어 추가될 때마다)
    |                                 |
    |--- 1010 판정결과 변경 -------->|  HMI에서 판정 변경 시
    |                                 |
```

### 3.2 Alive 체크 (30초 주기, 양방향)

```
[L2 Server]                     [SPL Client]
    |--- 1099 Alive (L2→SPL) ------->|  매 30초
    |<--- 1199 Alive (SPL→L2) -------|  매 30초
    |                                 |
```

### 3.3 비정상 연결 처리

- Alive 3회 연속 미수신 시 → 연결 끊김 감지 → 재접속 시도
- TCP 연결 끊김 감지 → 자동 재접속 (5초 대기 후)

---

## 4. 기존 코드 참고사항

`LLM_lv2_test.py`는 **기존 PyQt6 테스트 클라이언트**이며, SPL 측(클라이언트)에서 L2로 보내는 1101, 1199, 1010 전문을 수동 생성하는 UI 도구이다.

> **주의**: 이 코드에서 `ResultChange1010`은 SPL→L2가 아닌 L2→SPL 전문이지만, 테스트 편의상 클라이언트 측에서 빌드하도록 구현되어 있다. 실제 구현 시 방향에 주의할 것.

---

## 5. Agent별 상세 요구사항

### 5.1 Backend Agent

**역할**: L2 TCP Server + REST/WebSocket API Gateway

**핵심 기능**:
1. **TCP Server** (port 12147)
   - SPL 클라이언트 연결 수락
   - 수신 전문 파싱 (1101, 1199)
   - 송신 전문 빌드 (1001, 1002, 1010, 1099)
   - Alive 30초 주기 발신 + 수신 타임아웃 감지

2. **WebSocket API** (port 8080)
   - 프론트엔드로 실시간 이벤트 푸시
   - 권취상태 변경 시 즉시 브로드캐스트
   - 연결 상태 변경 이벤트

3. **REST API** (port 8080, 같은 FastAPI)
   - `POST /api/setup` — 생산정보 1001 전송
   - `POST /api/material` — 소재정보 1002 전송
   - `POST /api/result-change` — 판정결과 변경 1010 전송
   - `GET /api/status` — 현재 연결/가동 상태
   - `GET /api/coils` — 코일(번들) 목록 + 권취상태 이력

4. **데이터 관리**
   - 인메모리 저장 (SQLite 또는 dict)
   - 코일별 권취상태 이력 누적
   - 연결 이벤트 로그

### 5.2 Frontend Agent

**역할**: 산업용 모니터링 대시보드

**디자인 요구사항**:
- **Industrial Dark Theme** (SCADA 스타일)
- 컨트롤룸 미학: 데이터 밀도 높게, 장식 최소
- 상태 색상: 초록(정상) / 노랑(경고) / 빨강(위험) / 회색(오프라인)
- 폰트: `IBM Plex Sans` + `JetBrains Mono` (데이터값)

**화면 구성**:
1. **상단 Status Bar**: TCP 연결 상태, Alive 상태, 마지막 수신 시각
2. **좌측 사이드바**: 네비게이션 (대시보드, 코일목록, 설정, 로그)
3. **메인 대시보드**:
   - 현재 작업 코일 정보 카드 (번들번호, 강종, 제품명, 라인)
   - **25-Layer 권취상태 시각화** (핵심 위젯)
     - 25개 레이어를 그리드/스택으로 표현
     - N=초록, T=노랑, H=빨강, U=회색 으로 색상 구분
     - 실시간 업데이트 애니메이션
   - 생산/소재 정보 패널
   - Alive 카운터 + 가동상태 (A/B 라인)
4. **조작 패널**: 생산정보 전송, 소재정보 전송, 판정결과 변경
5. **로그 패널**: 전문 송수신 로그 (시간순, TC 코드별 필터)

### 5.3 Test Agent (SPL 시뮬레이터)

**역할**: 가상 SPL 장비 시뮬레이션 + 자동화 테스트

**시뮬레이터 기능**:
1. L2 서버에 TCP 클라이언트로 접속
2. 1199 Alive 주기적 발신 (30초)
3. 1001/1002 수신 시 파싱 & 표시
4. **자동 권취 시뮬레이션**:
   - 1002 소재정보 수신 후 자동으로 1101 권취상태를 단계적으로 발신
   - Layer 1부터 25까지 하나씩 추가하면서 상태 랜덤 생성 (N 80%, T 10%, H 5%, U 5%)
   - 각 레이어 간격: 2~5초 (설정 가능)
5. 1010 판정결과 변경 수신 & 확인

**자동화 테스트** (pytest):
1. **연결 테스트**: TCP 핸드셰이크, 연결/해제 사이클
2. **전문 빌드 테스트**: 모든 TC 코드에 대해 길이 검증, 패딩 검증
3. **전문 파싱 테스트**: 빌드→파싱 라운드트립 무결성
4. **패딩 검증 테스트**: 
   - 스페이스 패딩이 정확히 들어갔는지 (`spare` 필드 전체 스페이스 확인)
   - 숫자 필드 좌측 제로 패딩 확인
   - 문자열 필드 우측 스페이스 패딩 확인
   - 총 바이트 길이 정확성 확인
5. **시나리오 테스트**: 생산→소재→권취→판정변경 전체 플로우
6. **Alive 테스트**: 30초 주기 검증, 타임아웃 감지

---

## 6. 패딩 규칙 상세 (구현자 필독)

### 6.1 pad_right (문자열 필드)

```python
def pad_right(value: str, size: int) -> str:
    """우측 스페이스 패딩. 값이 size보다 길면 잘라냄."""
    value = str(value) if value else ""
    if len(value) > size:
        return value[:size]
    return value + " " * (size - len(value))
```

**사용 필드**: cBUNDLE_NO, cMTRL_NO1, cHEAT_NO, cSPEC_CD, cMAT_GRADE, cDIMS_NAME, cSPL_STATUS_MODn, spare

### 6.2 pad_left (숫자 필드)

```python
def pad_left(value: str, size: int) -> str:
    """좌측 '0' 패딩. 값이 size보다 길면 뒷부분만 취함."""
    value = str(value) if value else ""
    if len(value) > size:
        return value[-size:]
    return "0" * (size - len(value)) + value
```

**사용 필드**: cTcLength, cCount, cQTB_SPEED, cSPL_A_SPEED, cSPL_B_SPEED, cQTB_TEMP, cWork_A, cWork_B, cSPL_LAYER_COUNT

### 6.3 검증 함수 (반드시 구현)

```python
def validate_packet(raw: str, expected_len: int, tc: str) -> bool:
    """패킷 무결성 검증"""
    # 1) 총 길이
    assert len(raw) == expected_len, f"TC {tc}: expected {expected_len}, got {len(raw)}"
    
    # 2) TC 코드
    assert raw[0:4] == tc, f"TC mismatch: expected {tc}, got {raw[0:4]}"
    
    # 3) 날짜 형식 (14자리 숫자)
    assert raw[4:18].isdigit(), f"Date not numeric: {raw[4:18]}"
    
    # 4) 길이 필드
    length_field = raw[18:24]
    assert length_field.isdigit(), f"Length not numeric: {length_field}"
    assert int(length_field) == expected_len, f"Length field {length_field} != {expected_len}"
    
    # 5) ASCII 범위 확인
    assert all(32 <= ord(c) <= 126 for c in raw), "Non-ASCII character found"
    
    return True
```

### 6.4 스페이스 패딩 검증 예시

```python
def validate_spare(raw: str, offset: int, size: int) -> bool:
    """spare 필드가 전부 스페이스인지 확인"""
    spare = raw[offset:offset + size]
    assert len(spare) == size
    assert spare == " " * size, f"Spare not all spaces: {repr(spare)}"
    return True

# 예: 1001의 spare (offset 92, size 36)
validate_spare(packet_1001, 92, 36)
```

---

## 7. 디렉토리 구조

```
D:\DATA\python\LLM_LV2_TEST\
├── backend/
│   ├── main.py              # FastAPI + TCP Server 엔트리포인트
│   ├── tcp_server.py         # asyncio TCP Server
│   ├── protocol.py           # 전문 빌드/파싱 (공유 모듈)
│   ├── api_routes.py         # REST API 라우터
│   ├── ws_manager.py         # WebSocket 매니저
│   ├── data_store.py         # 인메모리 데이터 저장
│   └── requirements.txt
├── frontend/
│   ├── index.html            # SPA (단일 파일 또는 React)
│   ├── package.json          # (선택: React 빌드)
│   └── src/
│       ├── App.jsx
│       ├── components/
│       │   ├── StatusBar.jsx
│       │   ├── LayerGrid.jsx
│       │   ├── CoilInfo.jsx
│       │   ├── ControlPanel.jsx
│       │   └── LogPanel.jsx
│       └── hooks/
│           └── useWebSocket.js
├── spl_simulator/
│   ├── simulator.py          # SPL 시뮬레이터 본체
│   ├── protocol.py           # 전문 빌드/파싱 (backend와 공유)
│   ├── auto_winding.py       # 자동 권취 시뮬레이션 로직
│   └── requirements.txt
├── tests/
│   ├── test_protocol.py      # 전문 빌드/파싱 단위 테스트
│   ├── test_padding.py       # 패딩 검증 전용 테스트
│   ├── test_connection.py    # TCP 연결 테스트
│   ├── test_scenario.py      # 전체 시나리오 통합 테스트
│   └── conftest.py           # pytest fixtures
├── protocol.py               # 공용 프로토콜 모듈 (심볼릭 링크 또는 복사)
└── README.md
```

---

## 8. 기술 스택

| 구분 | 기술 | 버전 |
|------|------|------|
| Backend | Python | 3.11+ |
| Backend | FastAPI | 0.100+ |
| Backend | uvicorn | latest |
| Backend | websockets | (FastAPI 내장) |
| Frontend | React | 18+ |
| Frontend | Tailwind CSS | (CDN) |
| Frontend | Recharts | (차트) |
| Test | pytest | 7+ |
| Test | pytest-asyncio | latest |

---

## 9. 스펙 문서 오류 정리

| TC | 필드 | XLS 기재값 | 올바른 값 | 비고 |
|----|------|-----------|----------|------|
| 1001 | cTcLength | "000512" | "000128" | Tot=128 |
| 1002 | cTcLength | "000512" | "000256" | Tot=256 |
| 1010 | cTcLength | "000512" | "000576" | Tot=576, 기존 코드도 576 사용 |
| 1099 | cTcLength | "000050" | "000064" | Tot=64 |
| 1001 | cSPL_A_SPEED (10번) | "cSPL_A_SPEED" | "cSPL_B_SPEED" | B 선속인데 항목명이 A로 기재 |
