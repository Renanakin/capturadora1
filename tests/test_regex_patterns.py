"""Tests para extractores de fecha, monto, folio, RUT."""

from __future__ import annotations

from datetime import date

import pytest

from ocr_tributario.validators.regex_patterns import (
    extract_date,
    extract_folio,
    extract_rut,
    extract_total,
)


class TestExtractDate:
    @pytest.mark.parametrize("text,expected", [
        ("Fecha: 15/03/2024", date(2024, 3, 15)),
        ("Emitida 03-08-2023", date(2023, 8, 3)),
        ("DIA 7.11.2024", date(2024, 11, 7)),
        ("12 de marzo de 2024", date(2024, 3, 12)),
        ("5 de ene 2025", date(2025, 1, 5)),
    ])
    def test_valid(self, text, expected):
        assert extract_date(text) == expected

    def test_invalid_month(self):
        assert extract_date("99/99/2024") is None

    def test_empty(self):
        assert extract_date("") is None
        assert extract_date(None) is None


class TestExtractTotal:
    @pytest.mark.parametrize("text,expected", [
        ("TOTAL: $1.234.567", 1234567),
        ("Total 1234567", 1234567),
        ("TOTAL $12.500", 12500),
        ("Importe total  9.999", 9999),
    ])
    def test_valid(self, text, expected):
        assert extract_total(text) == expected

    def test_empty(self):
        assert extract_total("") is None
        assert extract_total(None) is None


class TestExtractFolio:
    @pytest.mark.parametrize("text,expected", [
        ("Factura N° 12345", 12345),
        ("BOLETA 9876543", 9876543),
        ("N° 555111", 555111),
    ])
    def test_valid(self, text, expected):
        assert extract_folio(text) == expected

    def test_empty(self):
        assert extract_folio("") is None


class TestExtractRut:
    @pytest.mark.parametrize("text", [
        "RUT: 12.345.678-5",
        "RUT 11111111-1",
        "R.U.T.: 22.222.222-2",
    ])
    def test_valid(self, text):
        out = extract_rut(text)
        assert out is not None
        assert "-" in out

    def test_invalid(self):
        assert extract_rut("Hola mundo sin RUT") is None
        assert extract_rut("Telefono 111111111") is None  # sin prefijo RUT