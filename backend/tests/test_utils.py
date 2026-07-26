"""Phone normalization — the format that must be right for both signup and M-Pesa."""

import pytest

from app.utils import normalize_kenyan_phone


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0712345678", "254712345678"),        # Safaricom 07
        ("0112345678", "254112345678"),        # Airtel/Equitel 01
        ("+254712345678", "254712345678"),     # international +
        ("254712345678", "254712345678"),      # already canonical
        ("712345678", "254712345678"),         # bare 9-digit
        ("  0712 345 678 ", "254712345678"),   # spaces
        ("0712-345-678", "254712345678"),      # dashes
    ],
)
def test_valid_numbers_normalize(raw, expected):
    assert normalize_kenyan_phone(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "123",              # too short
        "0812345678",       # 08 is not a KE mobile prefix
        "254812345678",     # same, canonical form
        "07123456789",      # too long
        "abcd",             # not digits
        "",                 # empty
    ],
)
def test_invalid_numbers_raise(raw):
    with pytest.raises(ValueError):
        normalize_kenyan_phone(raw)
