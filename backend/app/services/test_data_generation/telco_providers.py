"""Telco-specific Faker providers.

Faker doesn't ship realistic mobile / SIM / network identifiers. We add a small
provider that produces:

  msisdn    Mobile number (E.164) with realistic country dialling codes
  imsi      International Mobile Subscriber Identity (15 digits)
  imei      International Mobile Equipment Identity (15 digits, Luhn-valid)
  iccid     SIM card identifier (19-20 digits, Luhn-valid)
  lac       Location Area Code (1-65535)
  cell_id   Cell identifier (28-bit unsigned)
  tac       Tracking Area Code (16-bit unsigned)

Country codes follow ITU-T E.164. Calling `register_telco_providers(fake)`
registers them as bound methods on the supplied Faker instance.
"""
from __future__ import annotations

import random

from faker import Faker
from faker.providers import BaseProvider


# Mobile dial code -> typical national-significant-number length (range)
_COUNTRY_DIAL = {
    "IN": ("91", (10, 10)),
    "US": ("1", (10, 10)),
    "GB": ("44", (10, 10)),
    "AE": ("971", (9, 9)),
    "SA": ("966", (9, 9)),
    "SG": ("65", (8, 8)),
    "AU": ("61", (9, 9)),
    "DE": ("49", (10, 11)),
    "FR": ("33", (9, 9)),
    "JP": ("81", (10, 10)),
}

# IMSI Mobile Country Code prefixes (3 digits) for a few common operators
_IMSI_MCC = {
    "IN": "404",  # India
    "US": "310",
    "GB": "234",
    "AE": "424",
    "SA": "420",
    "SG": "525",
    "DE": "262",
    "FR": "208",
    "JP": "440",
}


def _luhn_check_digit(payload: str) -> str:
    """Standard Luhn algorithm: returns the single check digit for `payload`."""
    digits = [int(c) for c in payload]
    digits.reverse()
    total = 0
    for i, d in enumerate(digits):
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return str((10 - (total % 10)) % 10)


class TelcoProvider(BaseProvider):
    """Faker provider for telco identifiers."""

    def msisdn(self, country: str = "IN") -> str:
        country = (country or "IN").upper()
        cc, (lo, hi) = _COUNTRY_DIAL.get(country, ("91", (10, 10)))
        length = random.randint(lo, hi)
        # Mobile NSNs in most countries start 6-9; first digit non-zero.
        first = random.choice("6789")
        rest = "".join(str(random.randint(0, 9)) for _ in range(length - 1))
        return f"+{cc}{first}{rest}"

    def imsi(self, country: str = "IN", mnc: str | None = None) -> str:
        country = (country or "IN").upper()
        mcc = _IMSI_MCC.get(country, "404")
        mnc_value = mnc if mnc is not None else f"{random.randint(0, 999):03d}"
        # IMSI is 15 digits = MCC(3) + MNC(2 or 3) + MSIN
        msin_length = 15 - len(mcc) - len(mnc_value)
        msin = "".join(str(random.randint(0, 9)) for _ in range(msin_length))
        return f"{mcc}{mnc_value}{msin}"

    def imei(self) -> str:
        # IMEI structure: TAC(8) + SNR(6) + check(1), Luhn-valid.
        payload = "".join(str(random.randint(0, 9)) for _ in range(14))
        return payload + _luhn_check_digit(payload)

    def iccid(self) -> str:
        # ICCID typically 19 digits, last is Luhn check.
        # Major Industry Identifier "89" + MCC + issuer + serial + check digit.
        body = "89" + "".join(str(random.randint(0, 9)) for _ in range(16))
        return body + _luhn_check_digit(body)

    def lac(self) -> int:
        return random.randint(1, 65535)

    def cell_id(self) -> int:
        return random.randint(1, (1 << 28) - 1)

    def tac(self) -> int:
        return random.randint(1, 65535)


def register_telco_providers(fake: Faker) -> None:
    fake.add_provider(TelcoProvider)
