"""Key codes (contract 3.5 "Key codes"), with fictional names only."""

import tomllib
from concurrent.futures import ProcessPoolExecutor

import pytest
from click.testing import CliRunner

from gridmeta.cli.cli import cli
from gridmeta.codes import CODE, FEEDER_CODE, assign, load

TABLE = """\
[substations]
"maple/Maple Hill" = "AA"
"maple/Cedar Ridge" = "AB"
"birch/Oak Bend" = "AC"

[feeders]
"maple/Maple Hill/Feeder 1" = "AA-AA"
"maple/Maple Hill/Feeder 2" = "AA-AB"
"maple/Cedar Ridge/Feeder 1" = "AB-AA"

[areas]
"maple/North Valley" = "AA"
"""


@pytest.fixture
def table(tmp_path):
    path = tmp_path / "VT.toml"
    path.write_text(TABLE)
    return path


def single(tmp_path, text):
    path = tmp_path / "VT.toml"
    path.write_text(text)
    return path


def test_code(table):
    codes = load(table)
    assert codes.code("substation", "maple/Cedar Ridge") == "AB"
    assert codes.code("feeder", "maple/Maple Hill/Feeder 2") == "AA-AB"
    assert codes.code("area", "maple/North Valley") == "AA"


def test_missing_name_names_the_table(table):
    with pytest.raises(
        ValueError, match=r"VT\.toml: \[feeders\] has no code for 'maple/Maple Hill/X'"
    ):
        load(table).code("feeder", "maple/Maple Hill/X")


def test_unknown_kind_is_refused(table):
    with pytest.raises(ValueError, match=r"kind must be one of substation, feeder, area"):
        load(table).code("circuit", "maple/Maple Hill")


def test_assign_appends_the_next_code(table):
    assert assign(table, "substation", "birch/Elm Fork") == "AD"
    assert assign(table, "area", "birch/South Valley") == "AB"
    assert assign(table, "feeder", "maple/Maple Hill/Feeder 3") == "AA-AC"
    assert assign(table, "feeder", "birch/Elm Fork/Feeder 1") == "AD-AA"
    codes = load(table)
    assert codes.code("substation", "maple/Maple Hill") == "AA"
    assert codes.code("feeder", "birch/Elm Fork/Feeder 1") == "AD-AA"
    assert list(codes.tables["substations"]) == [
        "maple/Maple Hill",
        "maple/Cedar Ridge",
        "birch/Oak Bend",
        "birch/Elm Fork",
    ]


def test_utilities_of_a_state_share_one_sequence(table):
    """A second utility continues the state's sequence; the same name is a new key."""
    assert assign(table, "substation", "birch/Maple Hill") == "AD"
    assert assign(table, "feeder", "birch/Maple Hill/Feeder 1") == "AD-AA"


def test_existing_name_keeps_its_code(table):
    before = table.read_text()
    assert assign(table, "feeder", "maple/Cedar Ridge/Feeder 1") == "AB-AA"
    assert table.read_text() == before


def test_gap_is_never_filled(tmp_path):
    """A removed entry's code is not reused: the next code follows the last one used."""
    path = single(tmp_path, '[substations]\n"maple/Maple Hill" = "AC"\n')
    assert assign(path, "substation", "maple/Cedar Ridge") == "AD"


@pytest.mark.parametrize(
    "last, following",
    [("AZ", "BA"), ("ZZ", "AAA"), ("AAZ", "ABA"), ("AZZ", "BAA"), ("ZZZ", "AAAA")],
)
def test_codes_roll_over(tmp_path, last, following):
    path = single(tmp_path, f'[areas]\n"maple/North Valley" = "{last}"\n')
    assert assign(path, "area", "maple/South Valley") == following


def test_longer_codes_come_after_shorter_ones(tmp_path):
    path = single(tmp_path, '[substations]\n"maple/A" = "AAB"\n"maple/B" = "ZZ"\n')
    assert assign(path, "substation", "maple/C") == "AAC"


def test_three_letter_substation_gets_feeder_codes(tmp_path):
    path = single(tmp_path, '[substations]\n"maple/Maple Hill" = "AAB"\n')
    assert assign(path, "feeder", "maple/Maple Hill/Feeder 1") == "AAB-AA"
    assert load(path).code("feeder", "maple/Maple Hill/Feeder 1") == "AAB-AA"


def test_every_feeder_code_used_is_refused(tmp_path):
    text = '[substations]\n"maple/M" = "AA"\n[feeders]\n"maple/M/F1" = "AA-ZZ"\n'
    path = single(tmp_path, text)
    with pytest.raises(ValueError, match=r"substation AA has used every code from AA to ZZ"):
        assign(path, "feeder", "maple/M/F2")


def test_feeder_needs_its_substation_code(table):
    with pytest.raises(
        ValueError, match=r"'birch/Elm Fork/Feeder 1': substation 'birch/Elm Fork' has no code"
    ):
        assign(table, "feeder", "birch/Elm Fork/Feeder 1")


@pytest.mark.parametrize(
    "kind, name, shape",
    [
        ("substation", "Maple Hill", "<utility>/<substation>"),
        ("substation", "maple/Maple/Hill", "<utility>/<substation>"),
        ("area", "maple/", "<utility>/<area>"),
        ("feeder", "maple/Maple Hill", "<utility>/<substation>/<feeder>"),
        ("feeder", "maple/ /Feeder 1", "<utility>/<substation>/<feeder>"),
    ],
)
def test_assign_refuses_a_bad_key(table, kind, name, shape):
    before = table.read_text()
    with pytest.raises(ValueError, match=f'key must be "{shape}"'):
        assign(table, kind, name)
    assert table.read_text() == before


def test_empty_file_starts_at_aa(tmp_path):
    path = single(tmp_path, "")
    assert assign(path, "substation", "maple/Maple Hill") == "AA"
    assert assign(path, "feeder", "maple/Maple Hill/Feeder 1") == "AA-AA"
    assert tomllib.loads(path.read_text()) == {
        "substations": {"maple/Maple Hill": "AA"},
        "feeders": {"maple/Maple Hill/Feeder 1": "AA-AA"},
        "areas": {},
    }


def test_names_with_quotes_round_trip(tmp_path):
    path = single(tmp_path, "")
    assign(path, "substation", 'maple/Maple "Upper" Hill')
    assert assign(path, "feeder", 'maple/Maple "Upper" Hill/Feeder 1') == "AA-AA"
    assert load(path).code("substation", 'maple/Maple "Upper" Hill') == "AA"


def _assign_substation(path, index):
    return assign(path, "substation", f"utility{index % 3}/Substation {index}")


def test_concurrent_assigns_get_distinct_codes(tmp_path):
    path = single(tmp_path, "")
    with ProcessPoolExecutor(max_workers=8) as pool:
        codes = list(pool.map(_assign_substation, [path] * 40, range(40)))
    assert len(set(codes)) == 40
    assert sorted(load(path).tables["substations"].values()) == sorted(codes)


def test_patterns():
    assert all(CODE.match(code) for code in ["AA", "ZZ", "AAA", "ZZZZ"])
    assert not any(CODE.match(code) for code in ["A", "aa", "A1", "AA-AA"])
    assert all(FEEDER_CODE.match(code) for code in ["AA-AA", "AAB-ZZ"])
    assert not any(FEEDER_CODE.match(code) for code in ["AA-AAA", "A-AA", "AA-aa", "AAAA"])


@pytest.mark.parametrize(
    "text, message",
    [
        (
            '[substations]\n"maple/Maple Hill" = "aa"\n',
            r"'maple/Maple Hill': code 'aa' must be two or more upper-case",
        ),
        ('[areas]\n"maple/North Valley" = "A"\n', r"\[areas\] 'maple/North Valley': code 'A'"),
        ('[substations]\n"maple/Maple Hill" = 1\n', r"'maple/Maple Hill': code must be a string"),
        (
            '[substations]\n"maple/A" = "AA"\n"birch/B" = "AA"\n',
            r"'maple/A' and 'birch/B' have the same code AA",
        ),
        (
            '[substations]\n"maple/M" = "AA"\n[feeders]\n"maple/M/F" = "AB-AA"\n',
            r"'maple/M/F': code 'AB-AA' must be AA-<two upper-case letters>",
        ),
        (
            '[substations]\n"maple/M" = "AA"\n[feeders]\n"maple/M/F" = "AAAB"\n',
            r"code 'AAAB' must be AA-",
        ),
        (
            '[substations]\n"maple/M" = "AA"\n[feeders]\n"maple/M/F" = "AA-AAA"\n',
            r"code 'AA-AAA' must be AA-",
        ),
        (
            '[substations]\n"maple/M" = "AA"\n[feeders]\n'
            '"maple/M/F1" = "AA-AA"\n"maple/M/F2" = "AA-AA"\n',
            r"\[feeders\] 'maple/M/F1' and 'maple/M/F2' have the same code AA-AA",
        ),
        ('[feeders]\n"maple/M/F" = "AA-AA"\n', r"substation 'maple/M' has no code"),
        ('[substations]\n"Maple Hill" = "AA"\n', r'key must be "<utility>/<substation>"'),
        ('[areas]\n"maple/a/b" = "AA"\n', r'key must be "<utility>/<area>"'),
        ('[feeders]\n"maple/F" = "AA-AA"\n', r'key must be "<utility>/<substation>/<feeder>"'),
        ('[substations]\n"" = "AA"\n', r"\[substations\] \'\': key must be"),
        ("[circuits]\n", r"unknown tables \['circuits'\]"),
        ("substations = 1\n", r"substations must be a table"),
        ("[substations\n", r"not valid TOML"),
    ],
)
def test_invalid_table_is_refused(tmp_path, text, message):
    path = single(tmp_path, text)
    with pytest.raises(ValueError, match=rf"VT\.toml: .*{message}"):
        load(path)


@pytest.mark.parametrize("file_name", ["codes.toml", "vt.toml", "VTX.toml", "VT.json"])
def test_file_must_be_named_for_its_state(tmp_path, file_name):
    path = tmp_path / file_name
    path.write_text("")
    with pytest.raises(ValueError, match=r"must be named <STATE>\.toml"):
        load(path)
    with pytest.raises(ValueError, match=r"must be named <STATE>\.toml"):
        assign(path, "substation", "maple/Maple Hill")


def test_missing_table_file(tmp_path):
    with pytest.raises(ValueError, match=r"VT\.toml: file is missing"):
        load(tmp_path / "VT.toml")
    with pytest.raises(ValueError, match=r"VT\.toml: file is missing"):
        assign(tmp_path / "VT.toml", "substation", "maple/Maple Hill")


def test_cli_assign(table):
    result = CliRunner().invoke(
        cli, ["codes", "assign", str(table), "substation", "birch/Elm Fork"]
    )
    assert result.exit_code == 0, result.output
    assert result.output == "AD\n"
    result = CliRunner().invoke(cli, ["codes", "assign", str(table), "feeder", "birch/Oak/F"])
    assert result.exit_code != 0
    assert "has no code in [substations]" in result.output
