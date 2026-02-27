"""빌드→파싱 라운드트립 테스트"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.protocol import (
    TC1001_Setup, TC1002_Material, TC1010_ResultChange,
    TC1099_Alive, TC1101_WindingStatus, TC1199_Alive,
)


class TestRoundtrip1001:
    def test_fields_preserved(self, sample_1001):
        raw = sample_1001.build()
        parsed = TC1001_Setup.parse(raw)
        assert parsed.dims_name == sample_1001.dims_name
        assert parsed.spec_cd == sample_1001.spec_cd
        assert parsed.mat_grade == sample_1001.mat_grade
        assert parsed.qtb_speed == sample_1001.qtb_speed
        assert parsed.spl_a_speed == sample_1001.spl_a_speed
        assert parsed.spl_b_speed == sample_1001.spl_b_speed

    def test_length_preserved(self, sample_1001):
        raw1 = sample_1001.build()
        parsed = TC1001_Setup.parse(raw1)
        raw2 = parsed.build()
        assert len(raw1) == len(raw2)

    def test_byte_identical_except_date(self, sample_1001):
        raw1 = sample_1001.build()
        parsed = TC1001_Setup.parse(raw1)
        raw2 = parsed.build()
        assert raw1[:4] == raw2[:4]
        assert raw1[18:] == raw2[18:]


class TestRoundtrip1002:
    def test_fields_preserved(self, sample_1002):
        raw = sample_1002.build()
        parsed = TC1002_Material.parse(raw)
        assert parsed.bundle_no == sample_1002.bundle_no
        assert parsed.mtrl_no == sample_1002.mtrl_no
        assert parsed.heat_no == sample_1002.heat_no
        assert parsed.spec_cd == sample_1002.spec_cd
        assert parsed.mat_grade == sample_1002.mat_grade
        assert parsed.dims_name == sample_1002.dims_name
        assert parsed.line_no == sample_1002.line_no
        assert parsed.qtb_speed == sample_1002.qtb_speed
        assert parsed.spl_a_speed == sample_1002.spl_a_speed
        assert parsed.spl_b_speed == sample_1002.spl_b_speed
        assert parsed.qtb_temp == sample_1002.qtb_temp

    def test_byte_identical_except_date(self, sample_1002):
        raw1 = sample_1002.build()
        parsed = TC1002_Material.parse(raw1)
        raw2 = parsed.build()
        assert raw1[:4] == raw2[:4]
        assert raw1[18:] == raw2[18:]


class TestRoundtrip1010:
    def test_fields_preserved(self, sample_1010):
        raw = sample_1010.build()
        parsed = TC1010_ResultChange.parse(raw)
        assert parsed.bundle_no == sample_1010.bundle_no
        assert parsed.mtrl_no == sample_1010.mtrl_no
        assert parsed.line_no == sample_1010.line_no
        assert parsed.filenames[0] == sample_1010.filenames[0]
        assert parsed.filenames[1] == sample_1010.filenames[1]

    def test_byte_identical_except_date(self, sample_1010):
        raw1 = sample_1010.build()
        parsed = TC1010_ResultChange.parse(raw1)
        raw2 = parsed.build()
        assert raw1[:4] == raw2[:4]
        assert raw1[18:] == raw2[18:]


class TestRoundtrip1099:
    def test_fields_preserved(self, sample_1099):
        raw = sample_1099.build()
        parsed = TC1099_Alive.parse(raw)
        assert parsed.count == sample_1099.count

    def test_byte_identical_except_date(self, sample_1099):
        raw1 = sample_1099.build()
        parsed = TC1099_Alive.parse(raw1)
        raw2 = parsed.build()
        assert raw1[:4] == raw2[:4]
        assert raw1[18:] == raw2[18:]


class TestRoundtrip1101:
    def test_fields_preserved(self, sample_1101):
        raw = sample_1101.build()
        parsed = TC1101_WindingStatus.parse(raw)
        assert parsed.bundle_no == sample_1101.bundle_no
        assert parsed.mtrl_no == sample_1101.mtrl_no
        assert parsed.line_no == sample_1101.line_no
        assert parsed.layer_count == sample_1101.layer_count
        assert parsed.layers == sample_1101.layers

    def test_byte_identical_except_date(self, sample_1101):
        raw1 = sample_1101.build()
        parsed = TC1101_WindingStatus.parse(raw1)
        raw2 = parsed.build()
        assert raw1[:4] == raw2[:4]
        assert raw1[18:] == raw2[18:]


class TestRoundtrip1199:
    def test_fields_preserved(self, sample_1199):
        raw = sample_1199.build()
        parsed = TC1199_Alive.parse(raw)
        assert parsed.count == sample_1199.count
        assert parsed.work_a == sample_1199.work_a
        assert parsed.work_b == sample_1199.work_b

    def test_byte_identical_except_date(self, sample_1199):
        raw1 = sample_1199.build()
        parsed = TC1199_Alive.parse(raw1)
        raw2 = parsed.build()
        assert raw1[:4] == raw2[:4]
        assert raw1[18:] == raw2[18:]
