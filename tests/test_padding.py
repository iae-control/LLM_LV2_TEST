"""패딩 검증 전용 테스트 (★ 핵심)

SPL 측 개발자는 스페이스 패딩으로 길이를 맞추는 것을 선호하므로,
패딩이 정확하지 않으면 SPL이 파싱에 실패한다.
모든 TC의 모든 필드에 대해 패딩을 검증한다.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.protocol import (
    TC1001_Setup, TC1002_Material, TC1010_ResultChange,
    TC1099_Alive, TC1101_WindingStatus, TC1199_Alive,
)


# ===================================================================
# TC 1001 패딩 검증
# ===================================================================
class TestPadding1001:

    def test_short_string_right_padded(self):
        """짧은 문자열 → 우측 스페이스 채움"""
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
        assert raw[24:30] == "BL1600"
        assert len(raw) == 128

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

    def test_spec_cd_40_right_padded(self):
        """규격약호 40자리 우측 스페이스 패딩"""
        pkt = TC1001_Setup(spec_cd="KS SD600")
        raw = pkt.build()
        assert raw[30:70] == "KS SD600" + " " * 32

    def test_spec_cd_empty(self):
        pkt = TC1001_Setup(spec_cd="")
        raw = pkt.build()
        assert raw[30:70] == " " * 40

    def test_mat_grade_7_right_padded(self):
        """강종 7자리 우측 스페이스 패딩"""
        pkt = TC1001_Setup(mat_grade="C600CZ")
        raw = pkt.build()
        assert raw[70:77] == "C600CZ "

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

    def test_numeric_exact(self):
        """정확한 길이 숫자"""
        pkt = TC1001_Setup(qtb_speed="01513")
        raw = pkt.build()
        assert raw[77:82] == "01513"

    def test_spare_never_empty(self):
        """spare는 절대 빈 문자열이면 안 됨"""
        pkt = TC1001_Setup()
        raw = pkt.build()
        spare = raw[92:128]
        assert len(spare) == 36
        assert spare.strip() == ""
        assert spare == " " * 36

    def test_total_length_always_128(self):
        """어떤 입력이든 총 길이는 128"""
        for dims in ["", "A", "BL1600", "BL1600EXTRA"]:
            pkt = TC1001_Setup(dims_name=dims)
            raw = pkt.build()
            assert len(raw) == 128, f"dims={dims!r}: len={len(raw)}"

    def test_validate_padding_no_errors(self):
        pkt = TC1001_Setup(dims_name="BL1600", qtb_speed="01513",
                           spl_a_speed="01588", spl_b_speed="01588")
        raw = pkt.build()
        errors = TC1001_Setup.validate_padding(raw)
        assert errors == [], f"Validation errors: {errors}"


# ===================================================================
# TC 1002 패딩 검증
# ===================================================================
class TestPadding1002:

    def test_bundle_no_right_padded(self):
        pkt = TC1002_Material(bundle_no="S78588")
        raw = pkt.build()
        assert raw[24:34] == "S78588    ", f"Bundle not padded: {repr(raw[24:34])}"

    def test_bundle_no_exact(self):
        pkt = TC1002_Material(bundle_no="S78588B031")
        raw = pkt.build()
        assert raw[24:34] == "S78588B031"

    def test_mtrl_no_right_padded(self):
        pkt = TC1002_Material(mtrl_no="S78588069")
        raw = pkt.build()
        assert raw[34:44] == "S78588069 "

    def test_heat_no_right_padded(self):
        pkt = TC1002_Material(heat_no="S785")
        raw = pkt.build()
        assert raw[44:50] == "S785  "

    def test_line_no_single_char(self):
        pkt = TC1002_Material(line_no="A")
        raw = pkt.build()
        assert raw[103] == "A"
        assert len(raw) == 256

    def test_line_no_b(self):
        pkt = TC1002_Material(line_no="B")
        raw = pkt.build()
        assert raw[103] == "B"

    def test_qtb_temp_4_digits(self):
        pkt = TC1002_Material(qtb_temp="400")
        raw = pkt.build()
        assert raw[119:123] == "0400"

    def test_qtb_temp_empty(self):
        pkt = TC1002_Material(qtb_temp="")
        raw = pkt.build()
        assert raw[119:123] == "0000"

    def test_spare_133_bytes(self):
        pkt = TC1002_Material()
        raw = pkt.build()
        spare = raw[123:256]
        assert len(spare) == 133
        assert spare == " " * 133

    def test_total_length_always_256(self):
        pkt = TC1002_Material()
        raw = pkt.build()
        assert len(raw) == 256

    def test_validate_padding_no_errors(self):
        pkt = TC1002_Material(
            bundle_no="S78588B031", mtrl_no="S78588069", heat_no="S78588",
            line_no="A", qtb_speed="01513", spl_a_speed="01588",
            spl_b_speed="01588", qtb_temp="0400",
        )
        raw = pkt.build()
        errors = TC1002_Material.validate_padding(raw)
        assert errors == [], f"Validation errors: {errors}"


# ===================================================================
# TC 1010 패딩 검증
# ===================================================================
class TestPadding1010:

    def test_filename_50_chars_padded(self):
        fn = "20251230150001_C300ZZ_S73845B015_1_N.jpg"
        pkt = TC1010_ResultChange(filenames=[fn])
        raw = pkt.build()
        file1 = raw[45:95]
        assert len(file1) == 50
        assert file1.startswith(fn)
        assert file1 == fn + " " * (50 - len(fn))

    def test_filename_exact_50(self):
        fn = "X" * 50
        pkt = TC1010_ResultChange(filenames=[fn])
        raw = pkt.build()
        assert raw[45:95] == fn

    def test_filename_truncated_beyond_50(self):
        fn = "Y" * 60
        pkt = TC1010_ResultChange(filenames=[fn])
        raw = pkt.build()
        assert raw[45:95] == "Y" * 50
        assert len(raw) == 576

    def test_empty_filenames_all_spaces(self):
        pkt = TC1010_ResultChange(filenames=[])
        raw = pkt.build()
        for i in range(10):
            offset = 45 + i * 50
            field = raw[offset:offset + 50]
            assert field == " " * 50, f"File {i+1} not all spaces: {repr(field[:20])}..."

    def test_partial_filenames(self):
        """3개만 있으면 나머지 7개는 스페이스"""
        fns = ["file1.jpg", "file2.jpg", "file3.jpg"]
        pkt = TC1010_ResultChange(filenames=fns)
        raw = pkt.build()
        for i in range(3):
            offset = 45 + i * 50
            assert raw[offset:offset + 50].rstrip() == fns[i]
        for i in range(3, 10):
            offset = 45 + i * 50
            assert raw[offset:offset + 50] == " " * 50

    def test_spare_31_bytes(self):
        pkt = TC1010_ResultChange()
        raw = pkt.build()
        assert raw[545:576] == " " * 31

    def test_total_length_always_576(self):
        pkt = TC1010_ResultChange()
        raw = pkt.build()
        assert len(raw) == 576

    def test_validate_padding_no_errors(self):
        pkt = TC1010_ResultChange(bundle_no="S78588B031", mtrl_no="S78588069", line_no="A")
        raw = pkt.build()
        errors = TC1010_ResultChange.validate_padding(raw)
        assert errors == [], f"Validation errors: {errors}"


# ===================================================================
# TC 1099 패딩 검증
# ===================================================================
class TestPadding1099:

    def test_count_4_digits(self):
        pkt = TC1099_Alive(count=42)
        raw = pkt.build()
        assert raw[24:28] == "0042"

    def test_count_zero(self):
        pkt = TC1099_Alive(count=0)
        raw = pkt.build()
        assert raw[24:28] == "0000"

    def test_count_9999(self):
        pkt = TC1099_Alive(count=9999)
        raw = pkt.build()
        assert raw[24:28] == "9999"

    def test_count_overflow_reset(self):
        """9999 초과 시 0000 리셋"""
        pkt = TC1099_Alive(count=10000)
        raw = pkt.build()
        assert raw[24:28] == "0000"

    def test_count_large_overflow(self):
        pkt = TC1099_Alive(count=12345)
        raw = pkt.build()
        assert raw[24:28] == "2345"

    def test_spare_36_bytes(self):
        pkt = TC1099_Alive()
        raw = pkt.build()
        assert raw[28:64] == " " * 36

    def test_total_length_always_64(self):
        pkt = TC1099_Alive()
        raw = pkt.build()
        assert len(raw) == 64

    def test_validate_padding_no_errors(self):
        pkt = TC1099_Alive(count=1)
        raw = pkt.build()
        errors = TC1099_Alive.validate_padding(raw)
        assert errors == [], f"Validation errors: {errors}"


# ===================================================================
# TC 1101 패딩 검증
# ===================================================================
class TestPadding1101:

    def test_layer_count_2_digits(self):
        pkt = TC1101_WindingStatus(layer_count=5)
        raw = pkt.build()
        assert raw[45:47] == "05"

    def test_layer_count_25(self):
        pkt = TC1101_WindingStatus(layer_count=25)
        raw = pkt.build()
        assert raw[45:47] == "25"

    def test_layer_count_1(self):
        pkt = TC1101_WindingStatus(layer_count=1)
        raw = pkt.build()
        assert raw[45:47] == "01"

    def test_25_layer_chars(self):
        layers = ["N"] * 10 + ["T"] * 5 + ["H"] * 5 + ["U"] * 5
        pkt = TC1101_WindingStatus(layers=layers)
        raw = pkt.build()
        for i in range(25):
            assert raw[47 + i] in "NTHU", f"Layer {i+1} invalid: {repr(raw[47+i])}"

    def test_layers_specific_values(self):
        layers = ["N"] * 10 + ["T"] * 5 + ["H"] * 5 + ["U"] * 5
        pkt = TC1101_WindingStatus(layers=layers)
        raw = pkt.build()
        assert raw[47:57] == "N" * 10
        assert raw[57:62] == "T" * 5
        assert raw[62:67] == "H" * 5
        assert raw[67:72] == "U" * 5

    def test_bundle_no_right_padded(self):
        pkt = TC1101_WindingStatus(bundle_no="S78588")
        raw = pkt.build()
        assert raw[24:34] == "S78588    "

    def test_total_exactly_72(self):
        pkt = TC1101_WindingStatus()
        raw = pkt.build()
        assert len(raw) == 72

    def test_default_layers_all_N(self):
        pkt = TC1101_WindingStatus()
        raw = pkt.build()
        assert raw[47:72] == "N" * 25

    def test_validate_padding_no_errors(self):
        pkt = TC1101_WindingStatus(bundle_no="S78588B031", mtrl_no="S78588069",
                                   line_no="A", layer_count=25)
        raw = pkt.build()
        errors = TC1101_WindingStatus.validate_padding(raw)
        assert errors == [], f"Validation errors: {errors}"


# ===================================================================
# TC 1199 패딩 검증
# ===================================================================
class TestPadding1199:

    def test_count_4_digits(self):
        pkt = TC1199_Alive(count=1)
        raw = pkt.build()
        assert raw[24:28] == "0001"

    def test_work_a_b_format(self):
        pkt = TC1199_Alive(count=1, work_a="01", work_b="99")
        raw = pkt.build()
        assert raw[28:30] == "01"
        assert raw[30:32] == "99"

    def test_work_a_short_value(self):
        pkt = TC1199_Alive(work_a="1")
        raw = pkt.build()
        assert raw[28:30] == "01"

    def test_spare_20_bytes(self):
        pkt = TC1199_Alive()
        raw = pkt.build()
        assert raw[32:52] == " " * 20

    def test_total_length_always_52(self):
        pkt = TC1199_Alive()
        raw = pkt.build()
        assert len(raw) == 52

    def test_validate_padding_no_errors(self):
        pkt = TC1199_Alive(count=1, work_a="01", work_b="01")
        raw = pkt.build()
        errors = TC1199_Alive.validate_padding(raw)
        assert errors == [], f"Validation errors: {errors}"


# ===================================================================
# TC 간 공통 필드 패딩 일관성
# ===================================================================
class TestCrossTCPaddingConsistency:

    def test_bundle_no_same_across_tc(self):
        """같은 bundle_no가 1002, 1010, 1101에서 동일하게 패딩됨"""
        bn = "S78588"
        expected = "S78588    "

        raw_1002 = TC1002_Material(bundle_no=bn).build()
        raw_1010 = TC1010_ResultChange(bundle_no=bn).build()
        raw_1101 = TC1101_WindingStatus(bundle_no=bn).build()

        assert raw_1002[24:34] == expected
        assert raw_1010[24:34] == expected
        assert raw_1101[24:34] == expected

    def test_mtrl_no_same_across_tc(self):
        """같은 mtrl_no가 1002, 1010, 1101에서 동일하게 패딩됨"""
        mn = "S78588069"
        expected = "S78588069 "

        raw_1002 = TC1002_Material(mtrl_no=mn).build()
        raw_1010 = TC1010_ResultChange(mtrl_no=mn).build()
        raw_1101 = TC1101_WindingStatus(mtrl_no=mn).build()

        assert raw_1002[34:44] == expected
        assert raw_1010[34:44] == expected
        assert raw_1101[34:44] == expected

    def test_line_no_same_across_tc(self):
        """line_no가 1002(103), 1010(44), 1101(44)에서 동일"""
        raw_1002 = TC1002_Material(line_no="B").build()
        raw_1010 = TC1010_ResultChange(line_no="B").build()
        raw_1101 = TC1101_WindingStatus(line_no="B").build()

        assert raw_1002[103] == "B"
        assert raw_1010[44] == "B"
        assert raw_1101[44] == "B"

    def test_tc_length_field_consistent(self):
        """각 TC의 cTcLength 필드가 실제 총 길이와 일치"""
        cases = [
            (TC1001_Setup(), "000128", 128),
            (TC1002_Material(), "000256", 256),
            (TC1010_ResultChange(), "000576", 576),
            (TC1099_Alive(), "000064", 64),
            (TC1101_WindingStatus(), "000072", 72),
            (TC1199_Alive(), "000052", 52),
        ]
        for pkt, expected_len_str, expected_len_int in cases:
            raw = pkt.build()
            assert raw[18:24] == expected_len_str, f"TC {raw[0:4]}: {raw[18:24]} != {expected_len_str}"
            assert len(raw) == expected_len_int, f"TC {raw[0:4]}: len={len(raw)} != {expected_len_int}"
