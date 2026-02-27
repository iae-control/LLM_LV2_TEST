"""동국제강 CS공장 권취상태 모니터링 LV2 시스템 — 프로토콜 모듈

모든 TC(1001, 1002, 1010, 1099, 1101, 1199)의 빌드/파싱/패딩검증.
ASCII 고정길이 전문. 패딩 규칙:
  - 문자열(char) 필드: 우측 스페이스(' ') 패딩
  - 숫자형 필드: 좌측 '0' 패딩
  - spare 필드: 전체 스페이스(' ')
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


# ---------------------------------------------------------------------------
# 유틸리티
# ---------------------------------------------------------------------------

def now_14() -> str:
    """현재 시각 → YYYYMMDDhhmmss (14자리)"""
    return datetime.now().strftime("%Y%m%d%H%M%S")


def pad_right(value, size: int) -> str:
    """우측 스페이스 패딩. size 초과 시 잘라냄."""
    if value is None:
        value = ""
    else:
        value = str(value)
    if len(value) > size:
        return value[:size]
    return value + " " * (size - len(value))


def pad_left(value, size: int) -> str:
    """좌측 '0' 패딩. size 초과 시 뒷부분만 취함."""
    if value is None:
        value = ""
    else:
        value = str(value)
    if len(value) > size:
        return value[-size:]
    return "0" * (size - len(value)) + value


# TC 코드 → 전문 총 길이 매핑
TC_LENGTHS = {
    "1001": 128,
    "1002": 256,
    "1010": 576,
    "1099": 64,
    "1101": 72,
    "1199": 52,
}


def validate_packet(raw: str, expected_len: int, tc: str) -> bool:
    """공통 패킷 무결성 검증"""
    assert len(raw) == expected_len, f"TC {tc}: expected {expected_len}, got {len(raw)}"
    assert raw[0:4] == tc, f"TC mismatch: expected {tc}, got {raw[0:4]}"
    assert raw[4:18].isdigit(), f"Date not numeric: {raw[4:18]}"
    length_field = raw[18:24]
    assert length_field.isdigit(), f"Length not numeric: {length_field}"
    assert int(length_field) == expected_len, f"Length field {length_field} != {expected_len}"
    assert all(32 <= ord(c) <= 126 for c in raw), "Non-ASCII character found"
    return True


# ---------------------------------------------------------------------------
# TC 1001 — 생산정보 SETUP (L2→SPL), 128 bytes
# ---------------------------------------------------------------------------
# Offset | Field          | Size | Padding
# 0-3    | cTcCode        |  4   | -
# 4-17   | cDate          | 14   | -
# 18-23  | cTcLength      |  6   | 좌측 '0'
# 24-29  | cDIMS_NAME     |  6   | 우측 ' '
# 30-69  | cSPEC_CD       | 40   | 우측 ' '
# 70-76  | cMAT_GRADE     |  7   | 우측 ' '
# 77-81  | cQTB_SPEED     |  5   | 좌측 '0'
# 82-86  | cSPL_A_SPEED   |  5   | 좌측 '0'
# 87-91  | cSPL_B_SPEED   |  5   | 좌측 '0'
# 92-127 | spare          | 36   | 전체 ' '
# Total: 4+14+6+6+40+7+5+5+5+36 = 128

@dataclass
class TC1001_Setup:
    """생산정보 SETUP — TC 1001, Total 128 bytes"""
    TC = "1001"
    TOTAL_LEN = 128

    dims_name: str = ""
    spec_cd: str = ""
    mat_grade: str = ""
    qtb_speed: str = ""
    spl_a_speed: str = ""
    spl_b_speed: str = ""
    date: str = ""

    def build(self) -> str:
        msg = (
            self.TC                                  # [0:4]    4B
            + now_14()                               # [4:18]  14B
            + pad_left(str(self.TOTAL_LEN), 6)       # [18:24]  6B  "000128"
            + pad_right(self.dims_name, 6)           # [24:30]  6B
            + pad_right(self.spec_cd, 40)            # [30:70] 40B
            + pad_right(self.mat_grade, 7)           # [70:77]  7B
            + pad_left(self.qtb_speed, 5)            # [77:82]  5B
            + pad_left(self.spl_a_speed, 5)          # [82:87]  5B
            + pad_left(self.spl_b_speed, 5)          # [87:92]  5B
            + " " * 36                               # [92:128] 36B spare
        )
        assert len(msg) == self.TOTAL_LEN, f"TC1001 build: {len(msg)} != {self.TOTAL_LEN}"
        return msg

    @classmethod
    def parse(cls, raw: str) -> "TC1001_Setup":
        assert len(raw) == cls.TOTAL_LEN, f"TC1001 parse: expected {cls.TOTAL_LEN}, got {len(raw)}"
        assert raw[0:4] == cls.TC, f"TC1001 parse: expected '{cls.TC}', got '{raw[0:4]}'"
        return cls(
            date=raw[4:18],
            dims_name=raw[24:30].rstrip(),
            spec_cd=raw[30:70].rstrip(),
            mat_grade=raw[70:77].rstrip(),
            qtb_speed=raw[77:82],
            spl_a_speed=raw[82:87],
            spl_b_speed=raw[87:92],
        )

    @staticmethod
    def validate_padding(raw: str) -> list:
        errors = []
        if len(raw) != 128:
            errors.append(f"Total length: expected 128, got {len(raw)}")
            return errors
        if raw[0:4] != "1001":
            errors.append(f"TC code: expected '1001', got '{raw[0:4]}'")
        if not raw[4:18].isdigit():
            errors.append(f"Date not numeric: '{raw[4:18]}'")
        if raw[18:24] != "000128":
            errors.append(f"Length field: expected '000128', got '{raw[18:24]}'")
        spare = raw[92:128]
        if spare != " " * 36:
            errors.append(f"Spare not all spaces: {repr(spare)}")
        for name, s, e in [("cTcLength", 18, 24), ("cQTB_SPEED", 77, 82),
                           ("cSPL_A_SPEED", 82, 87), ("cSPL_B_SPEED", 87, 92)]:
            if not raw[s:e].isdigit():
                errors.append(f"{name} not all digits: '{raw[s:e]}'")
        return errors


# ---------------------------------------------------------------------------
# TC 1002 — 소재정보 (L2→SPL), 256 bytes
# ---------------------------------------------------------------------------
# Offset  | Field          | Size | Padding
# 0-3     | cTcCode        |  4   | -
# 4-17    | cDate          | 14   | -
# 18-23   | cTcLength      |  6   | 좌측 '0'
# 24-33   | cBUNDLE_NO     | 10   | 우측 ' '
# 34-43   | cMTRL_NO1      | 10   | 우측 ' '
# 44-49   | cHEAT_NO       |  6   | 우측 ' '
# 50-89   | cSPEC_CD       | 40   | 우측 ' '
# 90-96   | cMAT_GRADE     |  7   | 우측 ' '
# 97-102  | cDIMS_NAME     |  6   | 우측 ' '
# 103     | cLine_NO       |  1   | 없음
# 104-108 | cQTB_SPEED     |  5   | 좌측 '0'
# 109-113 | cSPL_A_SPEED   |  5   | 좌측 '0'
# 114-118 | cSPL_B_SPEED   |  5   | 좌측 '0'
# 119-122 | cQTB_TEMP      |  4   | 좌측 '0'
# 123-255 | spare          |133   | 전체 ' '
# Total: 4+14+6+10+10+6+40+7+6+1+5+5+5+4+133 = 256

@dataclass
class TC1002_Material:
    """소재정보 — TC 1002, Total 256 bytes"""
    TC = "1002"
    TOTAL_LEN = 256

    bundle_no: str = ""
    mtrl_no: str = ""
    heat_no: str = ""
    spec_cd: str = ""
    mat_grade: str = ""
    dims_name: str = ""
    line_no: str = "A"
    qtb_speed: str = ""
    spl_a_speed: str = ""
    spl_b_speed: str = ""
    qtb_temp: str = ""
    date: str = ""

    def build(self) -> str:
        msg = (
            self.TC                                  # [0:4]      4B
            + now_14()                               # [4:18]    14B
            + pad_left(str(self.TOTAL_LEN), 6)       # [18:24]    6B  "000256"
            + pad_right(self.bundle_no, 10)          # [24:34]   10B
            + pad_right(self.mtrl_no, 10)            # [34:44]   10B
            + pad_right(self.heat_no, 6)             # [44:50]    6B
            + pad_right(self.spec_cd, 40)            # [50:90]   40B
            + pad_right(self.mat_grade, 7)           # [90:97]    7B
            + pad_right(self.dims_name, 6)           # [97:103]   6B
            + (self.line_no or "A")[:1]              # [103:104]  1B
            + pad_left(self.qtb_speed, 5)            # [104:109]  5B
            + pad_left(self.spl_a_speed, 5)          # [109:114]  5B
            + pad_left(self.spl_b_speed, 5)          # [114:119]  5B
            + pad_left(self.qtb_temp, 4)             # [119:123]  4B
            + " " * 133                              # [123:256] 133B spare
        )
        assert len(msg) == self.TOTAL_LEN, f"TC1002 build: {len(msg)} != {self.TOTAL_LEN}"
        return msg

    @classmethod
    def parse(cls, raw: str) -> "TC1002_Material":
        assert len(raw) == cls.TOTAL_LEN, f"TC1002 parse: expected {cls.TOTAL_LEN}, got {len(raw)}"
        assert raw[0:4] == cls.TC, f"TC1002 parse: expected '{cls.TC}', got '{raw[0:4]}'"
        return cls(
            date=raw[4:18],
            bundle_no=raw[24:34].rstrip(),
            mtrl_no=raw[34:44].rstrip(),
            heat_no=raw[44:50].rstrip(),
            spec_cd=raw[50:90].rstrip(),
            mat_grade=raw[90:97].rstrip(),
            dims_name=raw[97:103].rstrip(),
            line_no=raw[103],
            qtb_speed=raw[104:109],
            spl_a_speed=raw[109:114],
            spl_b_speed=raw[114:119],
            qtb_temp=raw[119:123],
        )

    @staticmethod
    def validate_padding(raw: str) -> list:
        errors = []
        if len(raw) != 256:
            errors.append(f"Total length: expected 256, got {len(raw)}")
            return errors
        if raw[0:4] != "1002":
            errors.append(f"TC code: expected '1002', got '{raw[0:4]}'")
        if not raw[4:18].isdigit():
            errors.append(f"Date not numeric: '{raw[4:18]}'")
        if raw[18:24] != "000256":
            errors.append(f"Length field: expected '000256', got '{raw[18:24]}'")
        spare = raw[123:256]
        if spare != " " * 133:
            errors.append(f"Spare not all spaces (133B): {repr(spare[:30])}...")
        for name, s, e in [("cTcLength", 18, 24), ("cQTB_SPEED", 104, 109),
                           ("cSPL_A_SPEED", 109, 114), ("cSPL_B_SPEED", 114, 119),
                           ("cQTB_TEMP", 119, 123)]:
            if not raw[s:e].isdigit():
                errors.append(f"{name} not all digits: '{raw[s:e]}'")
        if raw[103] not in ("A", "B"):
            errors.append(f"Line_NO not A/B: '{raw[103]}'")
        return errors


# ---------------------------------------------------------------------------
# TC 1010 — 판정결과 변경 (L2→SPL), 576 bytes
# ---------------------------------------------------------------------------
# Offset  | Field              | Size | Padding
# 0-3     | cTcCode            |  4   | -
# 4-17    | cDate              | 14   | -
# 18-23   | cTcLength          |  6   | 좌측 '0'
# 24-33   | cBUNDLE_NO         | 10   | 우측 ' '
# 34-43   | cMTRL_NO1          | 10   | 우측 ' '
# 44      | cLine_NO           |  1   | 없음
# 45-94   | cSPL_STATUS_MOD1   | 50   | 우측 ' '
# 95-144  | cSPL_STATUS_MOD2   | 50   | 우측 ' '
# ...     | ...                | 50   | 우측 ' '
# 495-544 | cSPL_STATUS_MOD10  | 50   | 우측 ' '
# 545-575 | cSpare             | 31   | 전체 ' '
# Total: 4+14+6+10+10+1+(50×10)+31 = 576

@dataclass
class TC1010_ResultChange:
    """판정결과 변경 — TC 1010, Total 576 bytes"""
    TC = "1010"
    TOTAL_LEN = 576

    bundle_no: str = ""
    mtrl_no: str = ""
    line_no: str = "A"
    filenames: List[str] = field(default_factory=list)
    date: str = ""

    def build(self) -> str:
        # 파일명 10개 확보
        fns = list(self.filenames) + [""] * (10 - len(self.filenames))
        fns = fns[:10]

        files_str = "".join(pad_right(fn, 50) for fn in fns)

        msg = (
            self.TC                                  # [0:4]      4B
            + now_14()                               # [4:18]    14B
            + pad_left(str(self.TOTAL_LEN), 6)       # [18:24]    6B  "000576"
            + pad_right(self.bundle_no, 10)          # [24:34]   10B
            + pad_right(self.mtrl_no, 10)            # [34:44]   10B
            + (self.line_no or "A")[:1]              # [44:45]    1B
            + files_str                              # [45:545] 500B (50×10)
            + " " * 31                               # [545:576]  31B spare
        )
        assert len(msg) == self.TOTAL_LEN, f"TC1010 build: {len(msg)} != {self.TOTAL_LEN}"
        return msg

    @classmethod
    def parse(cls, raw: str) -> "TC1010_ResultChange":
        assert len(raw) == cls.TOTAL_LEN, f"TC1010 parse: expected {cls.TOTAL_LEN}, got {len(raw)}"
        assert raw[0:4] == cls.TC, f"TC1010 parse: expected '{cls.TC}', got '{raw[0:4]}'"
        filenames = []
        for i in range(10):
            offset = 45 + i * 50
            filenames.append(raw[offset:offset + 50].rstrip())
        return cls(
            date=raw[4:18],
            bundle_no=raw[24:34].rstrip(),
            mtrl_no=raw[34:44].rstrip(),
            line_no=raw[44],
            filenames=filenames,
        )

    @staticmethod
    def validate_padding(raw: str) -> list:
        errors = []
        if len(raw) != 576:
            errors.append(f"Total length: expected 576, got {len(raw)}")
            return errors
        if raw[0:4] != "1010":
            errors.append(f"TC code: expected '1010', got '{raw[0:4]}'")
        if not raw[4:18].isdigit():
            errors.append(f"Date not numeric: '{raw[4:18]}'")
        if raw[18:24] != "000576":
            errors.append(f"Length field: expected '000576', got '{raw[18:24]}'")
        spare = raw[545:576]
        if spare != " " * 31:
            errors.append(f"Spare not all spaces (31B): {repr(spare)}")
        if raw[44] not in ("A", "B"):
            errors.append(f"Line_NO not A/B: '{raw[44]}'")
        return errors


# ---------------------------------------------------------------------------
# TC 1099 — Alive (L2→SPL), 64 bytes
# ---------------------------------------------------------------------------
# Offset | Field     | Size | Padding
# 0-3    | cTcCode   |  4   | -
# 4-17   | cDate     | 14   | -
# 18-23  | cTcLength |  6   | 좌측 '0'
# 24-27  | cCount    |  4   | 좌측 '0'
# 28-63  | cSpare    | 36   | 전체 ' '
# Total: 4+14+6+4+36 = 64

@dataclass
class TC1099_Alive:
    """L2 Alive — TC 1099, Total 64 bytes"""
    TC = "1099"
    TOTAL_LEN = 64

    count: int = 0
    date: str = ""

    def build(self) -> str:
        count_val = int(self.count) % 10000
        msg = (
            self.TC                                  # [0:4]    4B
            + now_14()                               # [4:18]  14B
            + pad_left(str(self.TOTAL_LEN), 6)       # [18:24]  6B  "000064"
            + pad_left(str(count_val), 4)            # [24:28]  4B
            + " " * 36                               # [28:64] 36B spare
        )
        assert len(msg) == self.TOTAL_LEN, f"TC1099 build: {len(msg)} != {self.TOTAL_LEN}"
        return msg

    @classmethod
    def parse(cls, raw: str) -> "TC1099_Alive":
        assert len(raw) == cls.TOTAL_LEN, f"TC1099 parse: expected {cls.TOTAL_LEN}, got {len(raw)}"
        assert raw[0:4] == cls.TC, f"TC1099 parse: expected '{cls.TC}', got '{raw[0:4]}'"
        return cls(
            date=raw[4:18],
            count=int(raw[24:28]),
        )

    @staticmethod
    def validate_padding(raw: str) -> list:
        errors = []
        if len(raw) != 64:
            errors.append(f"Total length: expected 64, got {len(raw)}")
            return errors
        if raw[0:4] != "1099":
            errors.append(f"TC code: expected '1099', got '{raw[0:4]}'")
        if not raw[4:18].isdigit():
            errors.append(f"Date not numeric: '{raw[4:18]}'")
        if raw[18:24] != "000064":
            errors.append(f"Length field: expected '000064', got '{raw[18:24]}'")
        if not raw[24:28].isdigit():
            errors.append(f"Count not all digits: '{raw[24:28]}'")
        spare = raw[28:64]
        if spare != " " * 36:
            errors.append(f"Spare not all spaces (36B): {repr(spare)}")
        return errors


# ---------------------------------------------------------------------------
# TC 1101 — 권취상태 (SPL→L2), 72 bytes
# ---------------------------------------------------------------------------
# Offset | Field               | Size | Padding
# 0-3    | cTcCode             |  4   | -
# 4-17   | cDate               | 14   | -
# 18-23  | cTcLength           |  6   | 좌측 '0'
# 24-33  | cBUNDLE_NO          | 10   | 우측 ' '
# 34-43  | cMTRL_NO1           | 10   | 우측 ' '
# 44     | cLine_NO            |  1   | 없음
# 45-46  | cSPL_LAYER_COUNT    |  2   | 좌측 '0'
# 47-71  | cSPL_STATUS_LAYER1~25| 25  | 각 1B, 'N'/'T'/'H'/'U'
# Total: 4+14+6+10+10+1+2+25 = 72

@dataclass
class TC1101_WindingStatus:
    """권취상태 — TC 1101, Total 72 bytes"""
    TC = "1101"
    TOTAL_LEN = 72

    bundle_no: str = ""
    mtrl_no: str = ""
    line_no: str = "A"
    layer_count: int = 25
    layers: List[str] = field(default_factory=lambda: ["N"] * 25)
    date: str = ""

    def build(self) -> str:
        # 25개 레이어 확보
        full_layers = list(self.layers) + ["N"] * (25 - len(self.layers))
        full_layers = full_layers[:25]
        layers_str = "".join((s or "N")[:1] for s in full_layers)

        msg = (
            self.TC                                  # [0:4]    4B
            + now_14()                               # [4:18]  14B
            + pad_left(str(self.TOTAL_LEN), 6)       # [18:24]  6B  "000072"
            + pad_right(self.bundle_no, 10)          # [24:34] 10B
            + pad_right(self.mtrl_no, 10)            # [34:44] 10B
            + (self.line_no or "A")[:1]              # [44:45]  1B
            + pad_left(str(self.layer_count), 2)     # [45:47]  2B
            + layers_str                             # [47:72] 25B
        )
        assert len(msg) == self.TOTAL_LEN, f"TC1101 build: {len(msg)} != {self.TOTAL_LEN}"
        return msg

    @classmethod
    def parse(cls, raw: str) -> "TC1101_WindingStatus":
        assert len(raw) == cls.TOTAL_LEN, f"TC1101 parse: expected {cls.TOTAL_LEN}, got {len(raw)}"
        assert raw[0:4] == cls.TC, f"TC1101 parse: expected '{cls.TC}', got '{raw[0:4]}'"
        layers = [raw[47 + i] for i in range(25)]
        return cls(
            date=raw[4:18],
            bundle_no=raw[24:34].rstrip(),
            mtrl_no=raw[34:44].rstrip(),
            line_no=raw[44],
            layer_count=int(raw[45:47]),
            layers=layers,
        )

    @staticmethod
    def validate_padding(raw: str) -> list:
        errors = []
        if len(raw) != 72:
            errors.append(f"Total length: expected 72, got {len(raw)}")
            return errors
        if raw[0:4] != "1101":
            errors.append(f"TC code: expected '1101', got '{raw[0:4]}'")
        if not raw[4:18].isdigit():
            errors.append(f"Date not numeric: '{raw[4:18]}'")
        if raw[18:24] != "000072":
            errors.append(f"Length field: expected '000072', got '{raw[18:24]}'")
        if not raw[45:47].isdigit():
            errors.append(f"Layer count not digits: '{raw[45:47]}'")
        for i in range(25):
            ch = raw[47 + i]
            if ch not in "NTHU":
                errors.append(f"Layer {i+1} invalid char: '{ch}'")
        return errors


# ---------------------------------------------------------------------------
# TC 1199 — Alive (SPL→L2), 52 bytes
# ---------------------------------------------------------------------------
# Offset | Field     | Size | Padding
# 0-3    | cTcCode   |  4   | -
# 4-17   | cDate     | 14   | -
# 18-23  | cTcLength |  6   | 좌측 '0'
# 24-27  | cCount    |  4   | 좌측 '0'
# 28-29  | cWork_A   |  2   | 좌측 '0'
# 30-31  | cWork_B   |  2   | 좌측 '0'
# 32-51  | cSpare    | 20   | 전체 ' '
# Total: 4+14+6+4+2+2+20 = 52

@dataclass
class TC1199_Alive:
    """SPL Alive — TC 1199, Total 52 bytes"""
    TC = "1199"
    TOTAL_LEN = 52

    count: int = 0
    work_a: str = "01"
    work_b: str = "01"
    date: str = ""

    def build(self) -> str:
        count_val = int(self.count) % 10000
        msg = (
            self.TC                                  # [0:4]    4B
            + now_14()                               # [4:18]  14B
            + pad_left(str(self.TOTAL_LEN), 6)       # [18:24]  6B  "000052"
            + pad_left(str(count_val), 4)            # [24:28]  4B
            + pad_left(self.work_a, 2)               # [28:30]  2B
            + pad_left(self.work_b, 2)               # [30:32]  2B
            + " " * 20                               # [32:52] 20B spare
        )
        assert len(msg) == self.TOTAL_LEN, f"TC1199 build: {len(msg)} != {self.TOTAL_LEN}"
        return msg

    @classmethod
    def parse(cls, raw: str) -> "TC1199_Alive":
        assert len(raw) == cls.TOTAL_LEN, f"TC1199 parse: expected {cls.TOTAL_LEN}, got {len(raw)}"
        assert raw[0:4] == cls.TC, f"TC1199 parse: expected '{cls.TC}', got '{raw[0:4]}'"
        return cls(
            date=raw[4:18],
            count=int(raw[24:28]),
            work_a=raw[28:30],
            work_b=raw[30:32],
        )

    @staticmethod
    def validate_padding(raw: str) -> list:
        errors = []
        if len(raw) != 52:
            errors.append(f"Total length: expected 52, got {len(raw)}")
            return errors
        if raw[0:4] != "1199":
            errors.append(f"TC code: expected '1199', got '{raw[0:4]}'")
        if not raw[4:18].isdigit():
            errors.append(f"Date not numeric: '{raw[4:18]}'")
        if raw[18:24] != "000052":
            errors.append(f"Length field: expected '000052', got '{raw[18:24]}'")
        if not raw[24:28].isdigit():
            errors.append(f"Count not all digits: '{raw[24:28]}'")
        if not raw[28:30].isdigit():
            errors.append(f"Work_A not all digits: '{raw[28:30]}'")
        if not raw[30:32].isdigit():
            errors.append(f"Work_B not all digits: '{raw[30:32]}'")
        spare = raw[32:52]
        if spare != " " * 20:
            errors.append(f"Spare not all spaces (20B): {repr(spare)}")
        return errors


# ---------------------------------------------------------------------------
# TC 코드 → 파서 매핑
# ---------------------------------------------------------------------------
TC_PARSERS = {
    "1001": TC1001_Setup.parse,
    "1002": TC1002_Material.parse,
    "1010": TC1010_ResultChange.parse,
    "1099": TC1099_Alive.parse,
    "1101": TC1101_WindingStatus.parse,
    "1199": TC1199_Alive.parse,
}
