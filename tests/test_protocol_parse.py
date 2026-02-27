"""전문 파싱 테스트 — 빌드된 전문을 파싱하여 필드 정확성 검증"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.protocol import (
    TC1001_Setup, TC1002_Material, TC1010_ResultChange,
    TC1099_Alive, TC1101_WindingStatus, TC1199_Alive,
)


class TestParse1001:
    def test_parse_tc_code(self, sample_1001):
        raw = sample_1001.build()
        parsed = TC1001_Setup.parse(raw)
        assert parsed.date.isdigit()
        assert len(parsed.date) == 14

    def test_parse_dims_name(self, sample_1001):
        raw = sample_1001.build()
        parsed = TC1001_Setup.parse(raw)
        assert parsed.dims_name == "BL1600"

    def test_parse_spec_cd(self, sample_1001):
        raw = sample_1001.build()
        parsed = TC1001_Setup.parse(raw)
        assert parsed.spec_cd == "KS SD600"

    def test_parse_mat_grade(self, sample_1001):
        raw = sample_1001.build()
        parsed = TC1001_Setup.parse(raw)
        assert parsed.mat_grade == "C600CZ"

    def test_parse_speeds(self, sample_1001):
        raw = sample_1001.build()
        parsed = TC1001_Setup.parse(raw)
        assert parsed.qtb_speed == "01513"
        assert parsed.spl_a_speed == "01588"
        assert parsed.spl_b_speed == "01588"

    def test_parse_wrong_length_raises(self):
        with __import__("pytest").raises(AssertionError):
            TC1001_Setup.parse("1001" + "0" * 100)

    def test_parse_wrong_tc_raises(self):
        pkt = TC1001_Setup(dims_name="BL1600")
        raw = pkt.build()
        bad_raw = "9999" + raw[4:]
        with __import__("pytest").raises(AssertionError):
            TC1001_Setup.parse(bad_raw)


class TestParse1002:
    def test_parse_all_fields(self, sample_1002):
        raw = sample_1002.build()
        parsed = TC1002_Material.parse(raw)
        assert parsed.bundle_no == "S78588B031"
        assert parsed.mtrl_no == "S78588069"
        assert parsed.heat_no == "S78588"
        assert parsed.spec_cd == "KS SD600"
        assert parsed.mat_grade == "C600CZ"
        assert parsed.dims_name == "BL1600"
        assert parsed.line_no == "A"
        assert parsed.qtb_speed == "01513"
        assert parsed.spl_a_speed == "01588"
        assert parsed.spl_b_speed == "01588"
        assert parsed.qtb_temp == "0400"


class TestParse1010:
    def test_parse_filenames(self, sample_1010):
        raw = sample_1010.build()
        parsed = TC1010_ResultChange.parse(raw)
        assert parsed.bundle_no == "S78588B031"
        assert parsed.mtrl_no == "S78588069"
        assert parsed.line_no == "A"
        assert parsed.filenames[0] == "20251230150001_C300ZZ_S73845B015_1_N.jpg"
        assert parsed.filenames[1] == "20251230150001_C300ZZ_S73845B015_2_T.jpg"
        # 나머지 8개는 빈 문자열
        for i in range(2, 10):
            assert parsed.filenames[i] == ""


class TestParse1099:
    def test_parse_count(self, sample_1099):
        raw = sample_1099.build()
        parsed = TC1099_Alive.parse(raw)
        assert parsed.count == 42


class TestParse1101:
    def test_parse_all_fields(self, sample_1101):
        raw = sample_1101.build()
        parsed = TC1101_WindingStatus.parse(raw)
        assert parsed.bundle_no == "S78588B031"
        assert parsed.mtrl_no == "S78588069"
        assert parsed.line_no == "A"
        assert parsed.layer_count == 18
        assert len(parsed.layers) == 25
        assert parsed.layers[0] == "N"


class TestParse1199:
    def test_parse_all_fields(self, sample_1199):
        raw = sample_1199.build()
        parsed = TC1199_Alive.parse(raw)
        assert parsed.count == 41
        assert parsed.work_a == "01"
        assert parsed.work_b == "01"
