"""전문 빌드 테스트 — 모든 TC에 대해 빌드 결과 검증"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.protocol import (
    TC1001_Setup, TC1002_Material, TC1010_ResultChange,
    TC1099_Alive, TC1101_WindingStatus, TC1199_Alive,
)


class TestBuild1001:
    """TC 1001 생산정보 빌드 테스트"""

    def test_total_length(self, sample_1001):
        raw = sample_1001.build()
        assert len(raw) == 128

    def test_tc_code(self, sample_1001):
        raw = sample_1001.build()
        assert raw[0:4] == "1001"

    def test_date_format(self, sample_1001):
        raw = sample_1001.build()
        assert len(raw[4:18]) == 14
        assert raw[4:18].isdigit()

    def test_length_field(self, sample_1001):
        raw = sample_1001.build()
        assert raw[18:24] == "000128"

    def test_dims_name_padding(self, sample_1001):
        raw = sample_1001.build()
        assert raw[24:30] == "BL1600"
        assert len(raw[24:30]) == 6

    def test_spec_cd_padding(self, sample_1001):
        raw = sample_1001.build()
        spec = raw[30:70]
        assert len(spec) == 40
        assert spec.startswith("KS SD600")
        assert spec == "KS SD600" + " " * 32

    def test_mat_grade_padding(self, sample_1001):
        raw = sample_1001.build()
        mg = raw[70:77]
        assert len(mg) == 7
        assert mg == "C600CZ "

    def test_speed_zero_padding(self, sample_1001):
        raw = sample_1001.build()
        assert raw[77:82] == "01513"
        assert raw[82:87] == "01588"
        assert raw[87:92] == "01588"

    def test_spare_all_spaces(self, sample_1001):
        raw = sample_1001.build()
        spare = raw[92:128]
        assert len(spare) == 36
        assert spare == " " * 36

    def test_ascii_only(self, sample_1001):
        raw = sample_1001.build()
        for i, c in enumerate(raw):
            assert 32 <= ord(c) <= 126, f"Non-ASCII at offset {i}: {repr(c)}"


class TestBuild1002:
    """TC 1002 소재정보 빌드 테스트"""

    def test_total_length(self, sample_1002):
        raw = sample_1002.build()
        assert len(raw) == 256

    def test_tc_code(self, sample_1002):
        raw = sample_1002.build()
        assert raw[0:4] == "1002"

    def test_length_field(self, sample_1002):
        raw = sample_1002.build()
        assert raw[18:24] == "000256"

    def test_bundle_no(self, sample_1002):
        raw = sample_1002.build()
        assert raw[24:34] == "S78588B031"

    def test_mtrl_no(self, sample_1002):
        raw = sample_1002.build()
        assert raw[34:44] == "S78588069 "

    def test_heat_no(self, sample_1002):
        raw = sample_1002.build()
        assert raw[44:50] == "S78588"

    def test_spec_cd(self, sample_1002):
        raw = sample_1002.build()
        assert raw[50:90] == "KS SD600" + " " * 32

    def test_line_no(self, sample_1002):
        raw = sample_1002.build()
        assert raw[103] == "A"

    def test_speeds(self, sample_1002):
        raw = sample_1002.build()
        assert raw[104:109] == "01513"
        assert raw[109:114] == "01588"
        assert raw[114:119] == "01588"

    def test_qtb_temp(self, sample_1002):
        raw = sample_1002.build()
        assert raw[119:123] == "0400"

    def test_spare(self, sample_1002):
        raw = sample_1002.build()
        assert raw[123:256] == " " * 133

    def test_ascii_only(self, sample_1002):
        raw = sample_1002.build()
        for i, c in enumerate(raw):
            assert 32 <= ord(c) <= 126, f"Non-ASCII at offset {i}: {repr(c)}"


class TestBuild1010:
    """TC 1010 판정결과 변경 빌드 테스트"""

    def test_total_length(self, sample_1010):
        raw = sample_1010.build()
        assert len(raw) == 576

    def test_tc_code(self, sample_1010):
        raw = sample_1010.build()
        assert raw[0:4] == "1010"

    def test_length_field(self, sample_1010):
        raw = sample_1010.build()
        assert raw[18:24] == "000576"

    def test_bundle_no(self, sample_1010):
        raw = sample_1010.build()
        assert raw[24:34] == "S78588B031"

    def test_line_no(self, sample_1010):
        raw = sample_1010.build()
        assert raw[44] == "A"

    def test_filenames(self, sample_1010):
        raw = sample_1010.build()
        fn1 = "20251230150001_C300ZZ_S73845B015_1_N.jpg"
        assert raw[45:95].startswith(fn1)
        assert raw[45:95] == fn1 + " " * (50 - len(fn1))

    def test_spare(self, sample_1010):
        raw = sample_1010.build()
        assert raw[545:576] == " " * 31

    def test_ascii_only(self, sample_1010):
        raw = sample_1010.build()
        for i, c in enumerate(raw):
            assert 32 <= ord(c) <= 126, f"Non-ASCII at offset {i}: {repr(c)}"


class TestBuild1099:
    """TC 1099 L2 Alive 빌드 테스트"""

    def test_total_length(self, sample_1099):
        raw = sample_1099.build()
        assert len(raw) == 64

    def test_tc_code(self, sample_1099):
        raw = sample_1099.build()
        assert raw[0:4] == "1099"

    def test_length_field(self, sample_1099):
        raw = sample_1099.build()
        assert raw[18:24] == "000064"

    def test_count(self, sample_1099):
        raw = sample_1099.build()
        assert raw[24:28] == "0042"

    def test_spare(self, sample_1099):
        raw = sample_1099.build()
        assert raw[28:64] == " " * 36

    def test_ascii_only(self, sample_1099):
        raw = sample_1099.build()
        for i, c in enumerate(raw):
            assert 32 <= ord(c) <= 126, f"Non-ASCII at offset {i}: {repr(c)}"


class TestBuild1101:
    """TC 1101 권취상태 빌드 테스트"""

    def test_total_length(self, sample_1101):
        raw = sample_1101.build()
        assert len(raw) == 72

    def test_tc_code(self, sample_1101):
        raw = sample_1101.build()
        assert raw[0:4] == "1101"

    def test_length_field(self, sample_1101):
        raw = sample_1101.build()
        assert raw[18:24] == "000072"

    def test_bundle_no(self, sample_1101):
        raw = sample_1101.build()
        assert raw[24:34] == "S78588B031"

    def test_line_no(self, sample_1101):
        raw = sample_1101.build()
        assert raw[44] == "A"

    def test_layer_count(self, sample_1101):
        raw = sample_1101.build()
        assert raw[45:47] == "18"

    def test_layers(self, sample_1101):
        raw = sample_1101.build()
        for i in range(25):
            assert raw[47 + i] in "NTHU", f"Layer {i+1} invalid: {repr(raw[47+i])}"

    def test_ascii_only(self, sample_1101):
        raw = sample_1101.build()
        for i, c in enumerate(raw):
            assert 32 <= ord(c) <= 126, f"Non-ASCII at offset {i}: {repr(c)}"


class TestBuild1199:
    """TC 1199 SPL Alive 빌드 테스트"""

    def test_total_length(self, sample_1199):
        raw = sample_1199.build()
        assert len(raw) == 52

    def test_tc_code(self, sample_1199):
        raw = sample_1199.build()
        assert raw[0:4] == "1199"

    def test_length_field(self, sample_1199):
        raw = sample_1199.build()
        assert raw[18:24] == "000052"

    def test_count(self, sample_1199):
        raw = sample_1199.build()
        assert raw[24:28] == "0041"

    def test_work_a_b(self, sample_1199):
        raw = sample_1199.build()
        assert raw[28:30] == "01"
        assert raw[30:32] == "01"

    def test_spare(self, sample_1199):
        raw = sample_1199.build()
        assert raw[32:52] == " " * 20

    def test_ascii_only(self, sample_1199):
        raw = sample_1199.build()
        for i, c in enumerate(raw):
            assert 32 <= ord(c) <= 126, f"Non-ASCII at offset {i}: {repr(c)}"
