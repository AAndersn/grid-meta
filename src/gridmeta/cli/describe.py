from pathlib import Path

import click

from gridmeta.describe import InvalidPackage, describe, record_json


@click.command(name="describe")
@click.argument("package_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    "-o",
    "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Record file to write; standard output when not given.",
)
@click.option(
    "--reference-dir",
    envvar="GRIDMETA_REFERENCE_DIR",
    required=True,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Directory of the reference datasets and their SOURCES.toml "
    "(default: GRIDMETA_REFERENCE_DIR).",
)
def describe_package(package_dir: Path, output: Path | None, reference_dir: Path) -> None:
    """Write the feeder record of the feeder package PACKAGE_DIR."""
    try:
        record = describe(package_dir, reference_dir)
    except InvalidPackage as error:
        raise click.ClickException(
            f"{package_dir} is not a valid feeder package:\n{error}"
        ) from error
    text = record_json(record)
    if output is None:
        click.echo(text, nl=False)
    else:
        output.write_text(text)
