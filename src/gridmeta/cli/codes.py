from pathlib import Path

import click

from gridmeta import codes as key_codes


@click.group(name="codes")
def codes() -> None:
    """Key codes for substation, feeder and area names (<STATE>.toml, contract 3.5)."""


@codes.command(name="assign")
@click.argument("table", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("kind", type=click.Choice(list(key_codes.TABLES)))
@click.argument("name")
def assign(table: Path, kind: str, name: str) -> None:
    """Print the code of NAME, assigning the next one in TABLE when it has none. A feeder's NAME
    is "<utility>/<substation>/<feeder>"; a substation or area NAME is "<utility>/<name>"."""
    try:
        click.echo(key_codes.assign(table, kind, name))
    except ValueError as error:
        raise click.ClickException(str(error)) from error
