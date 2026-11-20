"""Keyed feeder, substation and distribution area identifiers (Grid Kitchen publishing contract,
section 2)."""

import hashlib
import hmac
import re

STATE_CODE = re.compile(r"^[A-Z]{2}$")
HEX_DIGITS = 10


def _digest(caller: str, names: dict[str, str], key: str) -> str:
    """The first 10 hex digits of HMAC-SHA256(key, the names joined with "/").

    Key and message are encoded as UTF-8. The same inputs always give the same digits.
    """
    for field, name in names.items():
        if not name:
            raise ValueError(f"{caller}: {field} name is empty")
    if not key:
        raise ValueError(f"{caller}: key is empty (set GK_MODEL_ID_KEY)")
    message = "/".join(names.values()).encode("utf-8")
    return hmac.new(key.encode("utf-8"), message, hashlib.sha256).hexdigest()[:HEX_DIGITS]


def _keyed_id(caller: str, state: str, names: dict[str, str], key: str) -> str:
    """`<ST>-<10 hex>`, with the digits from _digest."""
    if not STATE_CODE.match(state):
        raise ValueError(f"{caller}: state must be a two-letter USPS code, got {state!r}")
    return f"{state}-{_digest(caller, names, key)}"


def model_id(state: str, utility: str, substation: str, feeder: str, key: str) -> str:
    """The feeder's model id, from HMAC-SHA256(key, "<utility>/<substation>/<feeder>").

    The names are the source's own names, as in source.json. `key` is the secret
    GK_MODEL_ID_KEY.
    """
    names = {"utility": utility, "substation": substation, "feeder": feeder}
    return _keyed_id("model_id", state, names, key)


def sibling_group(state: str, utility: str, substation: str, key: str) -> str:
    """The substation's sibling group, from HMAC-SHA256(key, "<utility>/<substation>").

    Every feeder of one substation has the same group. The publisher names the substation
    series with it (dcat:inSeries).
    """
    names = {"utility": utility, "substation": substation}
    return _keyed_id("sibling_group", state, names, key)


def area_group(state: str, utility: str, distribution_area: str, key: str) -> str:
    """The distribution area's group, from HMAC-SHA256(key, "<utility>/area/<distribution area>").

    The literal "area" segment keeps an area apart from a substation of the same name. The group
    titles the area frame and keys the distribution area series (dcat:inSeries).
    """
    names = {"utility": utility, "segment": "area", "distribution_area": distribution_area}
    return _keyed_id("area_group", state, names, key)


def utility_code(utility: str, key: str) -> str:
    """The opaque utility code, from HMAC-SHA256(key, "<utility>"): 10 hex digits, no state.

    It stands for the utility in the authority IRI and, by default, as the model scope.
    """
    return _digest("utility_code", {"utility": utility}, key)
