"""M1: structural properties from the CIM data file (contract 4.2), one synthetic feeder per rule."""

from pathlib import Path

import cimprofiles.cim18.cim18v17_distribution as cim
import pytest
from cimgraph.databases import XMLFile
from cimgraph.models import NodeBreakerModel
from cimgraph.utils import write_json_ld

from gridmeta.structure import size_distribution, structural_properties, voltage_class
from synthetic import WGS84, FeederBuilder, example_feeder, use_profile

IEEE13_XML = Path(__file__).parent / "data" / "cim" / "ieee13.xml"
WC = cim.WindingConnection


def describe_feeder(feeder: FeederBuilder, tmp_path: Path) -> dict:
    return structural_properties(feeder.write(tmp_path / "VT-0a1b2c3d4e.jsonld"))


def test_example_feeder(tmp_path):
    record = describe_feeder(example_feeder(), tmp_path)
    assert record == {
        "gk:primaryVoltage": 12.47,
        "gk:voltageClass": 15,
        "gk:feederLength": 2.5,
        "gk:undergroundShare": 0.2,
        "gk:mvConnection": "gk:Connection.WyeGrounded",
        "gk:lvConnection": "gk:Connection.CenterTap",
        "gk:substationLTC": False,
        "gk:regulatorCount": 0,
        "gk:capacitorCount": 1,
        "gk:loadCount": 3,
        "gk:customerCount": 3,
        "gk:loadSizeDistribution": size_distribution([2.0, 3.0, 12.0]),
        "gk:dgCount": 1,
        "gk:dgCapacityAC": 7.6,
        "gk:dgSizeDistribution": size_distribution([7.6]),
        "gk:fuseCount": 1,
        "gk:recloserCount": 1,
        "gk:sectionalizerCount": 0,
        "gk:lowVoltageNetwork": False,
        "gk:secondaryModeling": "gk:SecondaryModeling.IndividualCustomers",
        "gk:geographicSpecificity": "gk:GeographicSpecificity.LatLong",
    }


@pytest.mark.parametrize(
    "primary_kv, expected",
    [(4.16, 5), (5.0, 5), (12.47, 15), (15.0, 15), (24.94, 25), (34.5, 35), (46.0, None)],
)
def test_voltage_class_edges(primary_kv, expected):
    assert voltage_class(primary_kv) == expected


def test_feeder_length_counts_only_primary_segments(tmp_path):
    feeder = FeederBuilder(primary_kv=24.94)
    feeder.line("head", "n1", 3.0)
    feeder.line("n1", "n2", 1.25)
    feeder.line("s1", "s2", 0.4, kv=0.24)
    record = describe_feeder(feeder, tmp_path)
    assert record["gk:primaryVoltage"] == 24.94
    assert record["gk:voltageClass"] == 25
    assert record["gk:feederLength"] == 4.25


def test_underground_share_is_unknown_when_a_wire_is_unknown(tmp_path):
    feeder = FeederBuilder()
    feeder.line("head", "n1", 1.0, wire=cim.ConcentricNeutralCableInfo)
    feeder.line("n1", "n2", 1.0)
    assert describe_feeder(feeder, tmp_path)["gk:undergroundShare"] is None


def test_size_bins_are_half_open():
    bins = size_distribution([0.0, 4.999, 5.0, 49.9, 50.0, 500.0, 5000.0, 6000.0])
    assert [size_bin["gk:share"] for size_bin in bins] == [0.25, 0.25, 0.13, 0.12, 0.25]
    assert [size_bin["gk:lowerBound"] for size_bin in bins] == [0, 5, 50, 500, 5000]
    assert "gk:upperBound" not in bins[-1]
    assert bins[0]["gk:upperBound"] == 5


def test_size_shares_add_up_to_one():
    bins = size_distribution([1.0] * 7 + [10.0] * 7 + [100.0] * 7)
    assert sum(size_bin["gk:share"] for size_bin in bins) == pytest.approx(1.0, abs=1e-9)


def test_unknown_values_are_left_out_not_zero(tmp_path):
    feeder = FeederBuilder()
    feeder.line("head", "n1", 1.0)
    feeder.load("n1", None, customers=None)
    feeder.generator("n1", None, kv=12.47)
    record = describe_feeder(feeder, tmp_path)
    assert record["gk:loadCount"] == 1
    assert record["gk:dgCount"] == 1
    unknown = [
        "gk:customerCount",
        "gk:loadSizeDistribution",
        "gk:dgCapacityAC",
        "gk:dgSizeDistribution",
        "gk:lvConnection",
    ]
    assert [record.get(key) for key in unknown] == [None] * len(unknown)


def test_no_loads_and_no_generators(tmp_path):
    feeder = FeederBuilder()
    feeder.line("head", "n1", 1.0)
    record = describe_feeder(feeder, tmp_path)
    assert record["gk:loadCount"] == 0
    assert record["gk:dgCount"] == 0
    assert record["gk:dgCapacityAC"] == 0
    unknown = ["gk:loadSizeDistribution", "gk:dgSizeDistribution", "gk:secondaryModeling"]
    assert [record.get(key) for key in unknown] == [None] * len(unknown)


def test_regulator_banks_not_single_phase_units(tmp_path):
    feeder = FeederBuilder()
    feeder.line("head", "n1", 1.0)
    for phase in (cim.SinglePhaseKind.A, cim.SinglePhaseKind.B, cim.SinglePhaseKind.C):
        feeder.regulator("n1", "n2", phase)
    feeder.regulator("n3", "n4", cim.SinglePhaseKind.A)
    record = describe_feeder(feeder, tmp_path)
    assert record["gk:regulatorCount"] == 2
    assert record["gk:substationLTC"] is False


def test_regulator_bank_at_the_feeder_head_is_the_substation_ltc(tmp_path):
    feeder = FeederBuilder()
    for phase in (cim.SinglePhaseKind.A, cim.SinglePhaseKind.B, cim.SinglePhaseKind.C):
        feeder.regulator("head", "n1", phase)
    feeder.regulator("n5", "n6", cim.SinglePhaseKind.A)
    record = describe_feeder(feeder, tmp_path)
    assert record["gk:regulatorCount"] == 1
    assert record["gk:substationLTC"] is True


def test_substation_transformer_ltc_is_not_a_regulator(tmp_path):
    feeder = FeederBuilder()
    feeder.source("hv", kv=115.0)
    feeder.transformer("hv", "bus", 115.0, 12.47, WC.D, WC.Yn, tap_changer=True)
    feeder.line("head", "n1", 1.0)
    record = describe_feeder(feeder, tmp_path)
    assert record["gk:substationLTC"] is True
    assert record["gk:regulatorCount"] == 0
    assert record["gk:hvConnection"] == "gk:Connection.Delta"
    assert record["gk:mvConnection"] == "gk:Connection.WyeGrounded"


def test_without_substation_transformer_mv_is_the_source_connection(tmp_path):
    feeder = FeederBuilder()
    feeder.source("bus", grounded=False)
    feeder.line("head", "n1", 1.0)
    record = describe_feeder(feeder, tmp_path)
    assert "gk:hvConnection" not in record
    assert record["gk:mvConnection"] == "gk:Connection.Wye"


def test_capacitor_banks_not_single_phase_units(tmp_path):
    feeder = FeederBuilder()
    feeder.line("head", "n1", 1.0)
    for _ in range(3):
        feeder.capacitor("n1")
    feeder.capacitor("n2")
    assert describe_feeder(feeder, tmp_path)["gk:capacitorCount"] == 2


def test_lv_connection_is_the_most_common_by_count(tmp_path):
    feeder = FeederBuilder()
    feeder.line("head", "n1", 1.0)
    feeder.center_tap("n1", "s1")
    feeder.transformer("n1", "s2", 12.47, 0.48, WC.Y, WC.Y)
    feeder.transformer("n1", "s3", 12.47, 0.48, WC.Y, WC.Yn)
    feeder.transformer("n1", "s4", 12.47, 0.208, WC.D, WC.Y, grounded2=True)
    assert describe_feeder(feeder, tmp_path)["gk:lvConnection"] == "gk:Connection.WyeGrounded"


def test_lv_connection_tie_goes_to_scheme_order(tmp_path):
    feeder = FeederBuilder()
    feeder.line("head", "n1", 1.0)
    feeder.center_tap("n1", "s1")
    feeder.transformer("n1", "s2", 12.47, 0.48, WC.D, WC.D)
    assert describe_feeder(feeder, tmp_path)["gk:lvConnection"] == "gk:Connection.Delta"


@pytest.mark.parametrize(
    "loads_at, expected",
    [
        ({"n1": 2}, "gk:SecondaryModeling.None"),
        ({"s1": 1, "s2": 1}, "gk:SecondaryModeling.AggregateLoad"),
        ({"s1": 3, "s2": 1}, "gk:SecondaryModeling.IndividualCustomers"),
    ],
)
def test_secondary_modeling(tmp_path, loads_at, expected):
    feeder = FeederBuilder()
    feeder.line("head", "n1", 1.0)
    feeder.center_tap("n1", "s1")
    feeder.center_tap("n1", "t2")
    feeder.line("t2", "s2", 0.03, kv=0.24, wire=cim.OverheadWireInfo)
    for node, count in loads_at.items():
        for _ in range(count):
            feeder.load(node, 3.0, kv=12.47 if node == "n1" else 0.24)
    record = describe_feeder(feeder, tmp_path)
    assert record["gk:secondaryModeling"] == expected
    assert record["gk:lowVoltageNetwork"] is False


def test_secondary_fed_by_two_transformers_is_a_low_voltage_network(tmp_path):
    feeder = FeederBuilder()
    feeder.line("head", "n1", 1.0)
    feeder.transformer("n1", "grid1", 12.47, 0.208, WC.D, WC.Yn)
    feeder.transformer("n1", "grid2", 12.47, 0.208, WC.D, WC.Yn)
    feeder.line("grid1", "grid2", 0.1, kv=0.208)
    feeder.load("grid2", 30.0, kv=0.208)
    assert describe_feeder(feeder, tmp_path)["gk:lowVoltageNetwork"] is True


def test_normally_open_secondary_tie_is_not_a_network(tmp_path):
    feeder = FeederBuilder()
    feeder.line("head", "n1", 1.0)
    feeder.transformer("n1", "grid1", 12.47, 0.208, WC.D, WC.Yn)
    feeder.transformer("n1", "grid2", 12.47, 0.208, WC.D, WC.Yn)
    feeder.switch(cim.LoadBreakSwitch, "grid1", "grid2", kv=0.208, normalOpen=True)
    assert describe_feeder(feeder, tmp_path)["gk:lowVoltageNetwork"] is False


@pytest.mark.parametrize(
    "crs, expected",
    [
        (WGS84, "gk:GeographicSpecificity.LatLong"),
        ("urn:ogc:def:crs:EPSG::4326", "gk:GeographicSpecificity.LatLong"),
        ("layout", "gk:GeographicSpecificity.XY"),
        (None, "gk:GeographicSpecificity.XY"),
    ],
)
def test_geographic_specificity(tmp_path, crs, expected):
    feeder = FeederBuilder()
    feeder.line("head", "n1", 1.0)
    feeder.position(crs)
    assert describe_feeder(feeder, tmp_path)["gk:geographicSpecificity"] == expected


def test_no_positions(tmp_path):
    feeder = FeederBuilder()
    feeder.line("head", "n1", 1.0)
    expected = "gk:GeographicSpecificity.None"
    assert describe_feeder(feeder, tmp_path)["gk:geographicSpecificity"] == expected


def test_protection_counts(tmp_path):
    feeder = FeederBuilder()
    feeder.line("head", "n1", 1.0)
    feeder.switch(cim.Recloser, "n1", "n2")
    feeder.switch(cim.Sectionaliser, "n2", "n3")
    for index in range(3):
        feeder.switch(cim.Fuse, "n3", f"tap{index}")
    feeder.switch(cim.LoadBreakSwitch, "n3", "n4")
    record = describe_feeder(feeder, tmp_path)
    assert (
        record["gk:fuseCount"],
        record["gk:recloserCount"],
        record["gk:sectionalizerCount"],
    ) == (
        3,
        1,
        1,
    )


def test_head_terminal_is_required(tmp_path):
    feeder = FeederBuilder()
    head = feeder.feeder.NormalHeadTerminal.pop()
    head.NormalHeadFeeder = None
    with pytest.raises(ValueError, match=r"VT-0a1b2c3d4e\.jsonld: cim:Feeder\.NormalHeadTerminal"):
        describe_feeder(feeder, tmp_path)


def test_segment_without_length_names_file_and_field(tmp_path):
    feeder = FeederBuilder()
    feeder.line("head", "n1", 1.0).length = None
    with pytest.raises(ValueError, match=r"\.jsonld: ACLineSegment .*cim:Conductor\.length"):
        describe_feeder(feeder, tmp_path)


def test_missing_data_file(tmp_path):
    with pytest.raises(ValueError, match=r"VT-0a1b2c3d4e\.jsonld: file is missing"):
        structural_properties(tmp_path / "VT-0a1b2c3d4e.jsonld")


def test_ieee13(tmp_path):
    """IEEE 13 (CIMHub CIM XML) written as JSON-LD, with the head breaker as the feeder head,
    which the CIM XML does not set."""
    use_profile()
    network = NodeBreakerModel(
        container=None, connection=XMLFile(str(IEEE13_XML)), distributed=False
    )
    (feeder,) = network.graph[cim.Feeder].values()
    (breaker,) = network.graph[cim.Breaker].values()
    head = next(t for t in breaker.Terminals if t.ConnectivityNode.name == "650")
    head.NormalHeadFeeder = feeder
    feeder.NormalHeadTerminal.append(head)
    path = tmp_path / "ieee13.jsonld"
    write_json_ld(network, str(path), convention="si", header={"dct:title": "ieee13"})
    record = structural_properties(path)
    assert record["gk:primaryVoltage"] == 4.16
    assert record["gk:voltageClass"] == 5
    assert record["gk:feederLength"] == 2.499  # 8,200 ft of line at 4.16 kV
    assert record["gk:undergroundShare"] is None  # impedances only, no wire data
    assert record["gk:hvConnection"] == "gk:Connection.Delta"
    assert record["gk:mvConnection"] == "gk:Connection.WyeGrounded"
    # The profile has no TransformerEndInfo.connectionKind, so the center-tapped tank's
    # secondary connection is unknown.
    assert record["gk:lvConnection"] is None
    # The three single-phase regulators at 650 are one bank, at the feeder head.
    assert record["gk:substationLTC"] is True
    assert record["gk:regulatorCount"] == 0
    assert record["gk:capacitorCount"] == 2
    assert record["gk:loadCount"] == 16
    assert record["gk:dgCount"] == 5
    assert record["gk:dgCapacityAC"] == 510.0
    assert (record["gk:fuseCount"], record["gk:recloserCount"]) == (1, 1)
    assert record["gk:sectionalizerCount"] == 0  # "sect1" is a LoadBreakSwitch
    assert record["gk:geographicSpecificity"] == "gk:GeographicSpecificity.XY"


@pytest.mark.parametrize(
    "connection, phases, expected",
    [
        (WC.Z, None, "Zigzag"),
        (WC.Zn, None, "Zigzag"),
        (WC.oY, None, "OpenWye"),
        (WC.oD, None, "OpenDelta"),
        (WC.I, cim.PhaseCode.s12N, "CenterTap"),
        (WC.I, cim.PhaseCode.AN, "SinglePhase"),
    ],
)
def test_secondary_connection_values(tmp_path, connection, phases, expected):
    feeder = FeederBuilder()
    feeder.line("head", "n1", 1.0)
    feeder.transformer("n1", "s1", 12.47, 0.24, WC.Y, connection, phases2=phases)
    record = describe_feeder(feeder, tmp_path)
    assert record["gk:lvConnection"] == f"gk:Connection.{expected}"
