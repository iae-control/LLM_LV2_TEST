# Claude Code Prompt: Test Agent (SPL 시뮬레이터 + 자동화 테스트)

> **이 프롬프트를 Claude Code에 입력하여 Test Agent를 구현하시오.**  
> **반드시 `PRD_LV2_SYSTEM.md`를 먼저 읽은 후 작업을 시작할 것.**

---

## 역할

너는 동국제강 CS공장 권취상태 모니터링 시스템의 **Test Agent** 개발자다.  
두 가지를 구현해야 한다:

1. **SPL 시뮬레이터** — 실제 SPL 장비를 대체하는 가상 TCP 클라이언트
2. **자동화 테스트** — 프로토콜 검증, 패딩 검증, 시나리오 테스트 (pytest)

## 작업 디렉토리

```
D:\DATA\python\LLM_LV2_TEST\
├── spl_simulator/    # SPL 시뮬레이터
└── tests/            # pytest 테스트
```

## 사전 조건

1. `PRD_LV2_SYSTEM.md`를 읽어라. 바이트 오프셋, 패딩 규칙이 거기에 있다.
2. `backend/protocol.py`를 import해서 사용하라. 프로토콜 모듈을 중복 구현하지 마라.
3. 기존 `LLM_lv2_test.py`는 참고용. 이건 수동 PyQt6 테스트 클라이언트이다.

---

## Part 1: SPL 시뮬레이터

### 개요

SPL 시뮬레이터는 실제 SPL(권취상태 모니터링 장비)을 흉내내는 TCP 클라이언트이다.  
L2 서버(Backend)에 접속하여 프로토콜 통신을 수행한다.

### 파일 구조

```
spl_simulator/
├── __init__.py
├── simulator.py          # 메인 시뮬레이터 클래스
├── auto_winding.py       # 자동 권취 시뮬레이션 엔진
├── cli.py                # CLI 인터페이스 (메뉴 기반)
└── requirements.txt
```

### simulator.py — 핵심 시뮬레이터

```python
import asyncio
import sys
sys.path.insert(0, '..')  # backend/protocol.py 접근
from backend.protocol import *

class SPLSimulator:
    """
    가상 SPL 클라이언트
    
    L2 서버에 TCP 접속 후:
    - Alive(1199) 30초 주기 발신
    - L2로부터 1001, 1002, 1010, 1099 수신 & 파싱
    - 수신한 소재정보(1002) 기반으로 자동 권취 시뮬레이션 시작
    """
    
    def __init__(self, host: str = "127.0.0.1", port: int = 12147):
        self.host = host
        self.port = port
        self.reader: asyncio.StreamReader = None
        self.writer: asyncio.StreamWriter = None
        self.alive_counter = 0
        self.work_a = "01"  # 정상
        self.work_b = "01"  # 정상
        self.connected = False
        self.current_material = None  # 수신한 1002 데이터
        self.winding_engine = None    # AutoWindingEngine 인스턴스
    
    async def connect(self):
        """L2 서버에 TCP 접속"""
        ...
    
    async def disconnect(self):
        """연결 종료"""
        ...
    
    async def send_alive(self):
        """TC 1199 Alive 발신"""
        self.alive_counter = (self.alive_counter + 1) % 10000
        # TC1199_Alive 빌드 → 전송
        ...
    
    async def alive_loop(self):
        """30초 주기 Alive 발신 루프"""
        while self.connected:
            await self.send_alive()
            await asyncio.sleep(30)
    
    async def receive_loop(self):
        """
        L2로부터 데이터 수신 루프
        
        [중요] TCP 스트림 파싱 로직:
        1. 최소 4바이트 읽기 → TC 코드 추출
        2. TC 코드로 전문 총 길이 결정
        3. 나머지 바이트 읽기
        4. 파싱 & 처리
        
        TC별 총 길이:
            "1001" → 128
            "1002" → 256
            "1010" → 576
            "1099" → 64
        """
        ...
    
    async def handle_setup(self, data: TC1001_Setup):
        """1001 생산정보 수신 처리"""
        print(f"[RX 1001] 제품명={data.dims_name} 강종={data.mat_grade}")
        ...
    
    async def handle_material(self, data: TC1002_Material):
        """
        1002 소재정보 수신 처리
        → 자동 권취 시뮬레이션 시작
        """
        self.current_material = data
        print(f"[RX 1002] 번들={data.bundle_no} 라인={data.line_no}")
        
        # 자동 권취 시작
        if self.winding_engine:
            self.winding_engine.cancel()
        self.winding_engine = AutoWindingEngine(self, data)
        asyncio.create_task(self.winding_engine.run())
    
    async def handle_result_change(self, data: TC1010_ResultChange):
        """1010 판정결과 변경 수신 처리"""
        print(f"[RX 1010] 번들={data.bundle_no} 파일수={sum(1 for f in data.filenames if f.strip())}")
        ...
    
    async def handle_alive(self, data: TC1099_Alive):
        """1099 L2 Alive 수신 처리"""
        print(f"[RX 1099] cnt={data.count}")
        ...
    
    async def send_winding_status(self, bundle_no, mtrl_no, line_no, layer_count, layers):
        """
        TC 1101 권취상태 발신
        
        layers: list of str, 각각 "N", "T", "H", "U"
        layer_count: 현재까지 감긴 레이어 수
        """
        # TC1101_WindingStatus 빌드 → 전송
        ...
```

### auto_winding.py — 자동 권취 시뮬레이션 엔진

```python
import random
import asyncio

class AutoWindingEngine:
    """
    소재정보(1002) 수신 후 자동으로 권취를 시뮬레이션하는 엔진.
    
    동작:
    1. Layer 1부터 시작
    2. 매 interval 초마다 새 레이어 추가
    3. 새 레이어의 상태를 확률적으로 결정
    4. 현재까지의 전체 레이어 상태를 TC 1101로 발신
    5. 25레이어까지 도달하면 종료
    
    상태 확률:
      N (Normal)     : 80%
      T (Twist)      : 10%
      H (Hooking)    : 5%
      U (Unmeasured) : 5%
    """
    
    def __init__(
        self,
        simulator: "SPLSimulator",
        material: "TC1002_Material",
        interval_range: tuple = (2.0, 5.0),  # 레이어 간 시간 (초)
        max_layers: int = 25,
        status_weights: dict = None,  # 상태별 가중치
    ):
        self.simulator = simulator
        self.material = material
        self.interval_range = interval_range
        self.max_layers = max_layers
        self.status_weights = status_weights or {
            "N": 80, "T": 10, "H": 5, "U": 5
        }
        self.layers: list[str] = []
        self.cancelled = False
    
    def cancel(self):
        self.cancelled = True
    
    def _random_status(self) -> str:
        """가중치 기반 랜덤 상태 생성"""
        population = list(self.status_weights.keys())
        weights = list(self.status_weights.values())
        return random.choices(population, weights=weights, k=1)[0]
    
    async def run(self):
        """
        권취 시뮬레이션 메인 루프
        
        매 스텝마다:
        1. 새 레이어 상태 생성
        2. layers 리스트에 추가
        3. TC 1101 전문 빌드 & 발신
           - layer_count = 현재 레이어 수
           - 나머지 (25 - 현재수) 레이어는 "N"으로 패딩
             (전문은 항상 25개 레이어를 포함해야 하므로)
        4. interval_range 범위 내 랜덤 대기
        5. 25개 도달 시 종료
        """
        print(f"[WINDING] 시뮬레이션 시작: 번들={self.material.bundle_no}")
        
        for i in range(self.max_layers):
            if self.cancelled:
                print("[WINDING] 취소됨")
                return
            
            # 새 레이어 상태
            status = self._random_status()
            self.layers.append(status)
            
            # 25개 슬롯으로 확장 (빈 자리는 "N" 패딩)
            full_layers = self.layers + ["N"] * (25 - len(self.layers))
            
            # 1101 발신
            await self.simulator.send_winding_status(
                bundle_no=self.material.bundle_no,
                mtrl_no=self.material.mtrl_no,
                line_no=self.material.line_no,
                layer_count=len(self.layers),
                layers=full_layers,
            )
            
            print(f"[WINDING] Layer {i+1}/25: {status} "
                  f"({'/'.join(self.layers)})")
            
            if i < self.max_layers - 1:
                delay = random.uniform(*self.interval_range)
                await asyncio.sleep(delay)
        
        print(f"[WINDING] 시뮬레이션 완료: {len(self.layers)} layers")
```

### cli.py — CLI 인터페이스

```python
"""
SPL 시뮬레이터 CLI

사용법:
  python -m spl_simulator.cli [--host HOST] [--port PORT]

메뉴:
  1. 서버 접속/해제
  2. Alive 상태 변경 (A/B 라인 정상/비정상)
  3. 수동 권취상태 발신 (레이어별 상태 지정)
  4. 자동 권취 시뮬레이션 시작/중지
  5. 시뮬레이션 속도 조절
  6. 현재 상태 표시
  7. 수신 로그 표시
  0. 종료
"""

# asyncio + CLI 입력을 동시에 처리해야 하므로,
# aioconsole 사용 또는 별도 스레드에서 input() 처리
```

### 실행

```bash
cd D:\DATA\python\LLM_LV2_TEST
python -m spl_simulator.cli
# 또는
python -m spl_simulator.cli --host 127.0.0.1 --port 12147
```

---

## Part 2: 자동화 테스트 (pytest)

### 파일 구조

```
tests/
├── __init__.py
├── conftest.py              # 공통 fixtures
├── test_protocol_build.py   # 전문 빌드 테스트
├── test_protocol_parse.py   # 전문 파싱 테스트
├── test_padding.py          # ★ 패딩 검증 전용
├── test_roundtrip.py        # 빌드→파싱 라운드트립
├── test_connection.py       # TCP 연결 테스트
└── test_scenario.py         # 통합 시나리오 테스트
```

### conftest.py — 공통 Fixtures

```python
import pytest
import asyncio
import sys
sys.path.insert(0, '..')

@pytest.fixture
def sample_1001():
    """1001 생산정보 샘플 데이터"""
    from backend.protocol import TC1001_Setup
    return TC1001_Setup(
        dims_name="BL1600",
        spec_cd="KS SD600",
        mat_grade="C600CZ",
        qtb_speed="01513",
        spl_a_speed="01588",
        spl_b_speed="01588",
    )

@pytest.fixture
def sample_1002():
    """1002 소재정보 샘플 데이터"""
    from backend.protocol import TC1002_Material
    return TC1002_Material(
        bundle_no="S78588B031",
        mtrl_no="S78588069",
        heat_no="S78588",
        spec_cd="KS SD600",
        mat_grade="C600CZ",
        dims_name="BL1600",
        line_no="A",
        qtb_speed="01513",
        spl_a_speed="01588",
        spl_b_speed="01588",
        qtb_temp="0400",
    )

# 나머지 TC도 마찬가지...

@pytest.fixture
async def backend_server():
    """
    테스트용 Backend 서버 시작/종료
    pytest-asyncio 사용
    """
    # backend의 TCP server를 테스트 포트에서 시작
    # yield
    # 서버 종료
    ...

@pytest.fixture
async def spl_client(backend_server):
    """
    테스트용 SPL 클라이언트 (시뮬레이터 경량 버전)
    """
    ...
```

### test_protocol_build.py — 빌드 테스트

```python
class TestBuild1001:
    """TC 1001 생산정보 빌드 테스트"""
    
    def test_total_length(self, sample_1001):
        raw = sample_1001.build()
        assert len(raw) == 128, f"Expected 128, got {len(raw)}"
    
    def test_tc_code(self, sample_1001):
        raw = sample_1001.build()
        assert raw[0:4] == "1001"
    
    def test_date_format(self, sample_1001):
        raw = sample_1001.build()
        date = raw[4:18]
        assert len(date) == 14
        assert date.isdigit()
    
    def test_length_field(self, sample_1001):
        raw = sample_1001.build()
        assert raw[18:24] == "000128"
    
    def test_dims_name_padding(self, sample_1001):
        """제품명 6자리 우측 스페이스 패딩"""
        raw = sample_1001.build()
        dims = raw[24:30]
        assert len(dims) == 6
        assert dims == "BL1600"  # 딱 6자라 패딩 없음
    
    def test_spec_cd_padding(self, sample_1001):
        """규격약호 40자리 우측 스페이스 패딩"""
        raw = sample_1001.build()
        spec = raw[30:70]
        assert len(spec) == 40
        assert spec.startswith("KS SD600")
        assert spec == "KS SD600" + " " * 32  # 나머지 스페이스
    
    def test_speed_zero_padding(self, sample_1001):
        """선속 5자리 좌측 제로 패딩"""
        raw = sample_1001.build()
        assert raw[77:82] == "01513"  # QTB
        assert raw[82:87] == "01588"  # SPL A
        assert raw[87:92] == "01588"  # SPL B
    
    def test_spare_all_spaces(self, sample_1001):
        """spare 36바이트 전체 스페이스"""
        raw = sample_1001.build()
        spare = raw[92:128]
        assert len(spare) == 36
        assert spare == " " * 36, f"Spare not all spaces: {repr(spare)}"
    
    def test_ascii_only(self, sample_1001):
        """ASCII 범위(32~126) 확인"""
        raw = sample_1001.build()
        for i, c in enumerate(raw):
            assert 32 <= ord(c) <= 126, f"Non-ASCII at offset {i}: {repr(c)} (ord={ord(c)})"


# TC 1002, 1010, 1099, 1101, 1199 각각에 대해 동일 패턴으로 작성
```

### test_padding.py — ★ 패딩 검증 전용 (핵심 테스트)

```python
"""
패딩 검증 전용 테스트.

SPL 측 개발자는 스페이스 패딩으로 길이를 맞추는 것을 선호하므로,
패딩이 정확하지 않으면 SPL이 파싱에 실패한다.

이 테스트는 모든 TC의 모든 필드에 대해 패딩을 검증한다.
"""

class TestPadding1001:
    """TC 1001 모든 필드 패딩 검증"""
    
    def test_short_string_right_padded(self):
        """짧은 문자열 → 우측 스페이스 채움"""
        # dims_name이 3자일 때
        pkt = TC1001_Setup(dims_name="BL1")
        raw = pkt.build()
        assert raw[24:30] == "BL1   ", f"Short string not right-padded: {repr(raw[24:30])}"
    
    def test_exact_length_string_no_padding(self):
        """정확한 길이 → 패딩 없음"""
        pkt = TC1001_Setup(dims_name="BL1600")
        raw = pkt.build()
        assert raw[24:30] == "BL1600"
    
    def test_long_string_truncated(self):
        """초과 길이 → 잘라냄"""
        pkt = TC1001_Setup(dims_name="BL1600EXTRA")
        raw = pkt.build()
        assert raw[24:30] == "BL1600"  # 6자까지만
        assert len(raw) == 128  # 총 길이 유지
    
    def test_empty_string_all_spaces(self):
        """빈 문자열 → 전체 스페이스"""
        pkt = TC1001_Setup(dims_name="")
        raw = pkt.build()
        assert raw[24:30] == "      ", f"Empty not all spaces: {repr(raw[24:30])}"
    
    def test_none_string_all_spaces(self):
        """None → 전체 스페이스"""
        pkt = TC1001_Setup(dims_name=None)
        raw = pkt.build()
        assert raw[24:30] == "      "
    
    def test_numeric_zero_padded(self):
        """숫자 필드 좌측 제로 패딩"""
        pkt = TC1001_Setup(qtb_speed="513")
        raw = pkt.build()
        assert raw[77:82] == "00513", f"Numeric not zero-padded: {repr(raw[77:82])}"
    
    def test_numeric_short_value(self):
        """짧은 숫자 → 좌측 제로 채움"""
        pkt = TC1001_Setup(qtb_speed="1")
        raw = pkt.build()
        assert raw[77:82] == "00001"
    
    def test_numeric_empty(self):
        """빈 숫자 → 전체 제로"""
        pkt = TC1001_Setup(qtb_speed="")
        raw = pkt.build()
        assert raw[77:82] == "00000"
    
    def test_spare_never_empty(self):
        """spare는 절대 빈 문자열이면 안 됨"""
        pkt = TC1001_Setup()
        raw = pkt.build()
        spare = raw[92:128]
        assert len(spare) == 36
        assert " " in spare  # 스페이스가 있어야 함
        assert spare.strip() == ""  # 내용은 없어야 함
        assert spare == " " * 36  # 정확히 스페이스만


class TestPadding1002:
    """TC 1002 모든 필드 패딩 검증"""
    
    def test_bundle_no_right_padded(self):
        pkt = TC1002_Material(bundle_no="S78588")
        raw = pkt.build()
        assert raw[24:34] == "S78588    ", f"Bundle not padded: {repr(raw[24:34])}"
    
    def test_line_no_single_char(self):
        """line_no는 정확히 1바이트"""
        pkt = TC1002_Material(line_no="A")
        raw = pkt.build()
        assert raw[103] == "A"
        assert len(raw) == 256
    
    def test_spare_133_bytes(self):
        """spare 133바이트 전체 스페이스"""
        pkt = TC1002_Material()
        raw = pkt.build()
        spare = raw[123:256]
        assert len(spare) == 133
        assert spare == " " * 133


class TestPadding1010:
    """TC 1010 판정결과 변경 패딩 검증"""
    
    def test_filename_50_chars_padded(self):
        """파일명 50자 우측 스페이스"""
        fn = "20251230150001_C300ZZ_S73845B015_1_N.jpg"
        pkt = TC1010_ResultChange(filenames=[fn])
        raw = pkt.build()
        file1 = raw[45:95]
        assert len(file1) == 50
        assert file1.startswith(fn)
        assert file1 == fn + " " * (50 - len(fn))
    
    def test_empty_filenames_all_spaces(self):
        """빈 파일명 10개 → 각각 50바이트 스페이스"""
        pkt = TC1010_ResultChange(filenames=[])
        raw = pkt.build()
        for i in range(10):
            offset = 45 + i * 50
            field = raw[offset:offset + 50]
            assert field == " " * 50, f"File {i+1} not all spaces: {repr(field[:20])}..."
    
    def test_spare_31_bytes(self):
        pkt = TC1010_ResultChange()
        raw = pkt.build()
        assert raw[545:576] == " " * 31


class TestPadding1099:
    """TC 1099 L2 Alive 패딩 검증"""
    
    def test_count_4_digits(self):
        pkt = TC1099_Alive(count=42)
        raw = pkt.build()
        assert raw[24:28] == "0042"
    
    def test_count_overflow_reset(self):
        """9999 초과 시 0000 리셋"""
        pkt = TC1099_Alive(count=10000)
        raw = pkt.build()
        assert raw[24:28] == "0000"
    
    def test_spare_36_bytes(self):
        pkt = TC1099_Alive()
        raw = pkt.build()
        assert raw[28:64] == " " * 36


class TestPadding1101:
    """TC 1101 권취상태 패딩 검증"""
    
    def test_layer_count_2_digits(self):
        pkt = TC1101_WindingStatus(layer_count=5)
        raw = pkt.build()
        assert raw[45:47] == "05"
    
    def test_25_layer_chars(self):
        """25개 레이어 상태가 각각 1바이트"""
        layers = ["N"] * 10 + ["T"] * 5 + ["H"] * 5 + ["U"] * 5
        pkt = TC1101_WindingStatus(layers=layers)
        raw = pkt.build()
        for i in range(25):
            assert raw[47 + i] in "NTHU", f"Layer {i+1} invalid: {repr(raw[47+i])}"
    
    def test_total_exactly_72(self):
        pkt = TC1101_WindingStatus()
        raw = pkt.build()
        assert len(raw) == 72


class TestPadding1199:
    """TC 1199 SPL Alive 패딩 검증"""
    
    def test_work_a_b_format(self):
        pkt = TC1199_Alive(count=1, work_a="01", work_b="99")
        raw = pkt.build()
        assert raw[28:30] == "01"
        assert raw[30:32] == "99"
    
    def test_spare_20_bytes(self):
        pkt = TC1199_Alive()
        raw = pkt.build()
        assert raw[32:52] == " " * 20


class TestCrossTCPaddingConsistency:
    """TC 간 공통 필드 패딩 일관성"""
    
    def test_bundle_no_same_across_tc(self):
        """같은 bundle_no가 1002, 1010, 1101에서 동일하게 패딩됨"""
        bn = "S78588"
        expected = "S78588    "  # 10자 우측 스페이스
        
        raw_1002 = TC1002_Material(bundle_no=bn).build()
        raw_1010 = TC1010_ResultChange(bundle_no=bn).build()
        raw_1101 = TC1101_WindingStatus(bundle_no=bn).build()
        
        assert raw_1002[24:34] == expected
        assert raw_1010[24:34] == expected
        assert raw_1101[24:34] == expected
```

### test_roundtrip.py — 빌드→파싱 라운드트립

```python
class TestRoundtrip:
    """빌드한 전문을 파싱했을 때 원본 데이터가 복원되는지 검증"""
    
    def test_1001_roundtrip(self, sample_1001):
        raw = sample_1001.build()
        parsed = TC1001_Setup.parse(raw)
        assert parsed.dims_name == sample_1001.dims_name
        assert parsed.spec_cd == sample_1001.spec_cd
        assert parsed.mat_grade == sample_1001.mat_grade
        # ... 모든 필드
    
    def test_1002_roundtrip(self, sample_1002):
        raw = sample_1002.build()
        parsed = TC1002_Material.parse(raw)
        assert parsed.bundle_no == sample_1002.bundle_no
        assert parsed.line_no == sample_1002.line_no
        # ... 모든 필드
    
    # 나머지 TC도 동일
    
    def test_roundtrip_preserves_length(self, sample_1001):
        """파싱 후 다시 빌드하면 길이 동일"""
        raw1 = sample_1001.build()
        parsed = TC1001_Setup.parse(raw1)
        raw2 = parsed.build()
        assert len(raw1) == len(raw2)
    
    def test_roundtrip_byte_identical(self, sample_1001):
        """
        빌드→파싱→빌드 시 바이트 동일
        (날짜 필드 제외 — 빌드 시마다 현재 시각이 들어가므로)
        """
        raw1 = sample_1001.build()
        parsed = TC1001_Setup.parse(raw1)
        raw2 = parsed.build()
        # 날짜 필드(4:18) 제외하고 비교
        assert raw1[:4] == raw2[:4]      # TC
        assert raw1[18:] == raw2[18:]    # 길이 + body (날짜만 다를 수 있음)
```

### test_scenario.py — 통합 시나리오 테스트

```python
@pytest.mark.asyncio
class TestFullScenario:
    """
    전체 플로우 시나리오 테스트:
    1. Backend 서버 시작
    2. SPL 시뮬레이터 접속
    3. L2 → SPL: 1001 생산정보 전송
    4. L2 → SPL: 1002 소재정보 전송
    5. SPL → L2: 1101 권취상태 수신 (자동 시뮬레이션)
    6. Alive 교환 확인
    7. L2 → SPL: 1010 판정결과 변경
    8. 연결 종료
    """
    
    async def test_full_production_cycle(self, backend_server, spl_client):
        # ... 위 시나리오 구현
        pass
    
    async def test_alive_timeout_detection(self, backend_server):
        """SPL이 Alive를 안 보내면 타임아웃 감지"""
        pass
    
    async def test_reconnection(self, backend_server):
        """SPL 재접속 시 정상 동작"""
        pass
```

### 실행

```bash
cd D:\DATA\python\LLM_LV2_TEST

# 전체 테스트
pytest tests/ -v

# 패딩 테스트만
pytest tests/test_padding.py -v

# 시나리오 테스트만 (서버 필요)
pytest tests/test_scenario.py -v

# SPL 시뮬레이터 실행
python -m spl_simulator.cli
```

## requirements.txt

```
# spl_simulator
asyncio  # (stdlib)

# tests
pytest>=7.0
pytest-asyncio>=0.21
```

## 주의사항

1. **protocol.py 중복 금지**: `backend/protocol.py`를 import해서 사용하라. 시뮬레이터에서 별도로 프로토콜을 재구현하면 불일치 발생 원인이 된다.
2. **패딩 테스트가 가장 중요**: SPL 개발자가 스페이스 패딩 기반으로 파싱하므로, 패딩이 1바이트라도 틀리면 통신 실패. `test_padding.py`가 전부 통과해야 안심할 수 있다.
3. **TCP 스트림 처리**: 시뮬레이터의 receive_loop에서 TCP 스트림을 전문 단위로 정확히 잘라내는 버퍼 로직을 꼭 구현하라.
4. **자동 권취 시뮬레이션**: 1002 수신 후 자동으로 돌아가야 테스트가 편하다. 수동 모드도 CLI에서 지원하되 기본은 자동.
