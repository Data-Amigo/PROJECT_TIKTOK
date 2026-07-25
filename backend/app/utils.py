"""
Small shared utilities. Pure functions, no I/O — trivial to test, safe to reuse.
"""

import re


def normalize_kenyan_phone(raw: str) -> str:
    """Turn any way a Kenyan enters their number into canonical `2547XXXXXXXX`
    (or `2541…` for the newer Airtel/Equitel range).

    Accepts: 0712345678, 0112345678, +254712345678, 254712345678, 712345678.
    Raises ValueError with a human message on anything that isn't a valid KE
    mobile number.

    WHY this matters beyond signup: M-Pesa's STK push (M4) requires the number
    in exactly `2547…` form. Normalizing once, at the border, means every phone
    in our DB is already payment-ready — we never guess a format later.
    """
    s = re.sub(r"[\s\-()]", "", raw.strip())
    if s.startswith("+"):
        s = s[1:]
    if not s.isdigit():
        raise ValueError("Phone number should contain only digits.")

    if s.startswith("0") and len(s) == 10:        # 0712345678 / 0112345678
        s = "254" + s[1:]
    elif len(s) == 9 and s[0] in "71":            # 712345678 / 112345678
        s = "254" + s
    # else: assume it's already 254… and let the final check validate it

    # Final gate: 254 + (7 or 1) + 8 digits. Rejects everything else clearly.
    if not re.fullmatch(r"254[71]\d{8}", s):
        raise ValueError("Enter a valid Kenyan phone number, e.g. 0712345678.")
    return s
