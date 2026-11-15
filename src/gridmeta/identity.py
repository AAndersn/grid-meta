"""Keyed feeder and substation identifiers (Grid Kitchen publishing contract, section 2)."""

import hashlib
import hmac
import re

STATE_CODE = re.compile(r"^[A-Z]{2}$")
HEX_DIGITS = 10


def _keyed_id(caller: str, state: str, names: dict[str, str], key: str) -> str:
    """`<ST>-<10 hex>`: HMAC-SHA256(key, the names joined with "/"), truncated.

    Key and message are encoded as UTF-8. The same inputs always give the same id.
    """
    if not STATE_CODE.match(state):
        raise ValueError(f"{caller}: state must be a two-letter USPS code, got {state!r}")
    for field, name in names.items():
        if not name:
            raise ValueError(f"{caller}: {field} name is empty")
    if not key:
        raise ValueError(f"{caller}: key is empty (set GK_MODEL_ID_KEY)")
    message = "/".join(names.values()).encode("utf-8")
    digest = hmac.new(key.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return f"{state}-{digest[:HEX_DIGITS]}"


def model_id(state: str, utility: str, substation: str, feeder: str, key: str) -> str:
    """The feeder's model id, from HMAC-SHA256(key, "<utility>/<substation>/<feeder>").

    The names are the source's own names, as in source.json. `key` is the secret
    GK_MODEL_ID_KEY.
    """
    names = {"utility": utility, "substation": substation, "feeder": feeder}
    return _keyed_id("model_id", state, names, key)


def sibling_group(state: str, utility: str, substation: str, key: str) -> str:
    """The substation's sibling group, from HMAC-SHA256(key, "<utility>/<substation>").

    Every feeder of one substation has the same group. The publisher writes it as
    gk:siblingGroup.
    """
    names = {"utility": utility, "substation": substation}
    return _keyed_id("sibling_group", state, names, key)
