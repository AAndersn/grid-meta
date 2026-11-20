"""Key codes for substation, feeder and distribution area names (publishing contract 3.5).

One private table per state, `gridpantry/datasets/codes/<STATE>.toml`, shared by every utility of
the state, maps each source name to its code:

    [substations]   "<utility>/<substation>" -> AA, AB, ... unique in the state
    [feeders]       "<utility>/<substation>/<feeder>" -> "<substation code>-<two letters>"
    [areas]         "<utility>/<area>" -> AA, AB, ... unique in the state

<utility> is the name of the utility's config directory (gridpantry/datasets/<utility>-configs).
The table is append-only: entries are never removed or edited. Codes are assigned after the last
one used, in AA ... ZZ, AAA, AAB ... order, with no end. Substation codes, area codes and each
substation's feeder codes are separate sequences; substation and area keys differ by prefix
(sub_AA, dist_area_AA). `assign` holds an exclusive lock on the file, so pipelines of several
utilities can share it.
"""

import fcntl
import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from gridmeta.identity import STATE_CODE

TABLES = {"substation": "substations", "feeder": "feeders", "area": "areas"}
SHAPES = {
    "substations": "<utility>/<substation>",
    "feeders": "<utility>/<substation>/<feeder>",
    "areas": "<utility>/<area>",
}
CODE = re.compile(r"^[A-Z]{2,}$")
FEEDER_CODE = re.compile(r"^([A-Z]{2,})-([A-Z]{2})$")
FIRST = "AA"
HEADER = (
    "# Key codes (Grid Kitchen publishing contract 3.5). Private: never shipped.\n"
    "# Written by `gridmeta codes assign`, which rewrites this file. Append-only: never remove or\n"
    "# edit an entry.\n"
)


@dataclass(frozen=True)
class Codes:
    """A loaded <STATE>.toml: table name -> source name -> code."""

    path: Path
    tables: dict[str, dict[str, str]]

    def code(self, kind: str, name: str) -> str:
        """The code of a name, keyed as in the module docstring."""
        table = _table(kind)
        if name not in self.tables[table]:
            raise ValueError(f"{self.path}: [{table}] has no code for {name!r}")
        return self.tables[table][name]


def _table(kind: str) -> str:
    if kind not in TABLES:
        raise ValueError(f"kind must be one of {', '.join(TABLES)}; got {kind!r}")
    return TABLES[kind]


def _check_path(path: Path) -> None:
    if path.suffix != ".toml" or not STATE_CODE.match(path.stem):
        raise ValueError(f"{path}: must be named <STATE>.toml, with a two-letter upper-case state")
    if not path.is_file():
        raise ValueError(f"{path}: file is missing")


def _check_key(path: Path, table: str, name: str) -> None:
    parts = name.split("/")
    if len(parts) != SHAPES[table].count("/") + 1 or not all(part.strip() for part in parts):
        raise ValueError(
            f'{path}: [{table}] {name!r}: key must be "{SHAPES[table]}", with no empty part'
        )


def _substation_of(path: Path, substations: dict[str, str], feeder: str) -> str:
    """The code of a feeder's substation, which must have one."""
    substation = feeder.rsplit("/", 1)[0]
    if substation not in substations:
        raise ValueError(
            f"{path}: [feeders] {feeder!r}: substation {substation!r} has no code in [substations]"
        )
    return substations[substation]


def _check_unique(path: Path, table: str, entries: dict[str, str]) -> None:
    names_by_code = {}
    for name, code in entries.items():
        if code in names_by_code:
            raise ValueError(
                f"{path}: [{table}] {names_by_code[code]!r} and {name!r} have the same code {code}"
            )
        names_by_code[code] = name


def _validate(path: Path, data: dict) -> dict[str, dict[str, str]]:
    unknown = sorted(set(data) - set(TABLES.values()))
    if unknown:
        raise ValueError(f"{path}: unknown tables {unknown}; expected {list(TABLES.values())}")
    tables = {table: data.get(table, {}) for table in TABLES.values()}
    for table, entries in tables.items():
        if not isinstance(entries, dict):
            raise ValueError(f"{path}: {table} must be a table")
        for name, code in entries.items():
            _check_key(path, table, name)
            if not isinstance(code, str):
                raise ValueError(f"{path}: [{table}] {name!r}: code must be a string")
    for table in ("substations", "areas"):
        for name, code in tables[table].items():
            if not CODE.match(code):
                raise ValueError(
                    f"{path}: [{table}] {name!r}: code {code!r} must be two or more upper-case "
                    "letters"
                )
        _check_unique(path, table, tables[table])
    for feeder, code in tables["feeders"].items():
        substation_code = _substation_of(path, tables["substations"], feeder)
        match = FEEDER_CODE.match(code)
        if match is None or match.group(1) != substation_code:
            raise ValueError(
                f"{path}: [feeders] {feeder!r}: code {code!r} must be {substation_code}-<two "
                "upper-case letters>"
            )
    _check_unique(path, "feeders", tables["feeders"])
    return tables


def _parse(path: Path, text: str) -> Codes:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"{path}: not valid TOML: {error}") from error
    return Codes(path, _validate(path, data))


def load(path: Path) -> Codes:
    """Read and validate a <STATE>.toml, under a shared lock."""
    path = Path(path)
    _check_path(path)
    with path.open() as file:
        fcntl.flock(file, fcntl.LOCK_SH)
        return _parse(path, file.read())


def _successor(code: str) -> str:
    """The code after `code`: AB after AA, BA after AZ, AAA after ZZ."""
    if code == "Z" * len(code):
        return "A" * (len(code) + 1)
    head = code.rstrip("Z")
    return head[:-1] + chr(ord(head[-1]) + 1) + "A" * (len(code) - len(head))


def _next_code(used: list[str]) -> str:
    """The code after the last one used, ordered by length and then by letters; AA when none is."""
    if not used:
        return FIRST
    return _successor(max(used, key=lambda code: (len(code), code)))


def _toml(tables: dict[str, dict[str, str]]) -> str:
    """The table as TOML. A JSON string is a TOML basic string."""
    sections = []
    for table, entries in tables.items():
        lines = [f"[{table}]"]
        lines += [
            f"{json.dumps(name, ensure_ascii=False)} = {json.dumps(code)}"
            for name, code in entries.items()
        ]
        sections.append("\n".join(lines) + "\n")
    return HEADER + "\n" + "\n".join(sections)


def assign(path: Path, kind: str, name: str) -> str:
    """The code of a name, assigning and writing the next one when the name has none. A feeder
    gets its substation's code and the next pair in that substation; the substation must have a
    code. The file is read and rewritten under an exclusive lock."""
    path = Path(path)
    _check_path(path)
    table = _table(kind)
    with path.open("r+") as file:
        fcntl.flock(file, fcntl.LOCK_EX)
        codes = _parse(path, file.read())
        entries = codes.tables[table]
        if name in entries:
            return entries[name]
        _check_key(path, table, name)
        if kind == "feeder":
            prefix = _substation_of(path, codes.tables["substations"], name) + "-"
            suffix = _next_code(
                [code.removeprefix(prefix) for code in entries.values() if code.startswith(prefix)]
            )
            if len(suffix) > len(FIRST):
                raise ValueError(
                    f"{path}: [feeders] substation {prefix[:-1]} has used every code from AA to ZZ"
                )
            code = prefix + suffix
        else:
            code = _next_code(list(entries.values()))
        tables = {**codes.tables, table: {**entries, name: code}}
        text = _toml(tables)
        if tomllib.loads(text) != tables:
            raise ValueError(f"{path}: [{table}] {name!r} does not survive a TOML round trip")
        file.seek(0)
        file.truncate()
        file.write(text)
    return code
