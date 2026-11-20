import click

from gridmeta.cli.codes import codes
from gridmeta.cli.converter import extract_opendss_dehydrated_dataset
from gridmeta.cli.describe import describe_package


@click.group()
def cli():
    pass


cli.add_command(extract_opendss_dehydrated_dataset)
cli.add_command(describe_package)
cli.add_command(codes)
