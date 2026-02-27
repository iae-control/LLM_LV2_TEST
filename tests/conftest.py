"""pytest 공통 fixtures"""

import sys
import os
import pytest

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.protocol import (
    TC1001_Setup, TC1002_Material, TC1010_ResultChange,
    TC1099_Alive, TC1101_WindingStatus, TC1199_Alive,
)


@pytest.fixture
def sample_1001():
    """TC 1001 생산정보 샘플"""
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
    """TC 1002 소재정보 샘플"""
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


@pytest.fixture
def sample_1010():
    """TC 1010 판정결과 변경 샘플"""
    return TC1010_ResultChange(
        bundle_no="S78588B031",
        mtrl_no="S78588069",
        line_no="A",
        filenames=[
            "20251230150001_C300ZZ_S73845B015_1_N.jpg",
            "20251230150001_C300ZZ_S73845B015_2_T.jpg",
        ],
    )


@pytest.fixture
def sample_1099():
    """TC 1099 L2 Alive 샘플"""
    return TC1099_Alive(count=42)


@pytest.fixture
def sample_1101():
    """TC 1101 권취상태 샘플"""
    return TC1101_WindingStatus(
        bundle_no="S78588B031",
        mtrl_no="S78588069",
        line_no="A",
        layer_count=18,
        layers=["N"] * 15 + ["T"] * 3 + ["H"] * 2 + ["U"] * 5,
    )


@pytest.fixture
def sample_1199():
    """TC 1199 SPL Alive 샘플"""
    return TC1199_Alive(count=41, work_a="01", work_b="01")
