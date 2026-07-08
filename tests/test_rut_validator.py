"""Tests para validador RUT (Módulo 11)."""

from __future__ import annotations

import pytest

from ocr_tributario.validators.rut import (
    clean_rut,
    format_rut,
    validate_rut,
)


class TestCleanRut:
    def test_basic(self):
        assert clean_rut("12345678-5") == "123456785"

    def test_with_dots(self):
        assert clean_rut("12.345.678-5") == "123456785"

    def test_lowercase_k(self):
        assert clean_rut("12345678k") == "12345678K"

    def test_empty(self):
        assert clean_rut("") is None
        assert clean_rut(None) is None

    def test_only_letters(self):
        assert clean_rut("abc") is None


class TestValidateRut:
    @pytest.mark.parametrize("raw,expected", [
        ("12345678-5", "12.345.678-5"),
        ("11111111-1", "11.111.111-1"),
        ("22222222-2", "22.222.222-2"),
        # 40 → DV=K (0*2 + 4*3 = 12; 12%11=1; 11-1=10 → K)
        ("40K", "40-K"),
        ("40-k", "40-K"),
    ])
    def test_valid(self, raw, expected):
        assert validate_rut(raw) == expected

    @pytest.mark.parametrize("raw", [
        "12345678-9",   # DV malo
        "11111111-2",   # DV malo
        "99999999-0",   # DV malo
        "1234",
        "",
        "abcdefg-h",
    ])
    def test_invalid(self, raw):
        assert validate_rut(raw) is None

    def test_format_output(self):
        out = validate_rut("12345678-5")
        assert out is not None
        assert format_rut(out.replace(".", "").replace("-", "")) == "12.345.678-5"