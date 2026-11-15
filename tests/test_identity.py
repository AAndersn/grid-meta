"""model_id and sibling_group (contract section 2)."""

import pytest

from gridmeta.identity import model_id, sibling_group

NAMES = ("Example Electric Cooperative", "Example Substation", "Example Feeder 1")
KEY = "gridmeta-test-key"


def test_vector():
    # printf '%s' 'Example Electric Cooperative/Example Substation/Example Feeder 1' \
    #   | openssl dgst -sha256 -hmac 'gridmeta-test-key'   -> a7e58062b1...
    assert model_id("VT", *NAMES, key=KEY) == "VT-a7e58062b1"


def test_depends_on_key_and_names():
    assert model_id("VT", *NAMES, key="another-key") != model_id("VT", *NAMES, key=KEY)
    assert model_id("VT", NAMES[0], NAMES[1], "Example Feeder 2", key=KEY) != model_id(
        "VT", *NAMES, key=KEY
    )


@pytest.mark.parametrize(
    "state, names, key, message",
    [
        ("vt", NAMES, KEY, "state"),
        ("VT", ("", NAMES[1], NAMES[2]), KEY, "utility"),
        ("VT", (NAMES[0], NAMES[1], ""), KEY, "feeder"),
        ("VT", NAMES, "", "GK_MODEL_ID_KEY"),
    ],
)
def test_invalid_input_is_rejected(state, names, key, message):
    with pytest.raises(ValueError, match=message):
        model_id(state, *names, key=key)


def test_sibling_group_vector():
    # printf '%s' 'Example Electric Cooperative/Example Substation' \
    #   | openssl dgst -sha256 -hmac 'gridmeta-test-key'   -> c9941857f9...
    assert sibling_group("VT", NAMES[0], NAMES[1], key=KEY) == "VT-c9941857f9"


def test_sibling_group_is_shared_by_the_substation_feeders():
    assert sibling_group("VT", NAMES[0], NAMES[1], key=KEY) != model_id("VT", *NAMES, key=KEY)
    assert sibling_group("VT", NAMES[0], "Other Substation", key=KEY) != sibling_group(
        "VT", NAMES[0], NAMES[1], key=KEY
    )


@pytest.mark.parametrize(
    "state, names, key, message",
    [
        ("Vermont", NAMES[:2], KEY, "sibling_group: state"),
        ("VT", (NAMES[0], ""), KEY, "substation"),
        ("VT", NAMES[:2], "", "GK_MODEL_ID_KEY"),
    ],
)
def test_invalid_sibling_group_input_is_rejected(state, names, key, message):
    with pytest.raises(ValueError, match=message):
        sibling_group(state, *names, key=key)
