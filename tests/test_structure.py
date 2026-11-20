"""M1: structural properties from the package's CIM models (contract 3.5 and 4.2), one synthetic
feeder per rule."""

from pathlib import Path

import cimprofiles.cim18.cim18v17 as cim
import pytest
from cimgraph.databases import XMLFile
from cimgraph.models import NodeBreakerModel

from gridmeta.structure import size_distribution, structural_properties, voltage_class
from synthetic import MODEL_ID, WGS84, FeederBuilder, example_feeder, use_profile, write_models

IEEE13_XML = Path(__file__).parent / "data" / "cim" / "ieee13.xml"
WC = cim.WindingConnection


def describe_feeder(feeder: FeederBuilder, tmp_path: Path) -> dict:
    return structural_properties(feeder.write(tmp_path / "jsonld"), MODEL_ID)


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


def test_template_tank_end_is_skipped(tmp_path):
    """A TransformerTankConfiguration's ends, with no Terminal, are catalogue data (CIMHub's GLM
    importer), not ends of a transformer."""
    feeder = example_feeder()
    configuration = feeder.add(cim.TransformerTankConfiguration(mRID=feeder.mrid()))
    for number in (1, 2):
        feeder.add(
            cim.TransformerTankEnd(
                mRID=feeder.mrid(),
                endNumber=number,
                TankConfiguration=configuration,
            )
        )
    expected = describe_feeder(example_feeder(), tmp_path / "plain")
    assert describe_feeder(feeder, tmp_path / "template") == expected


def test_tank_end_with_no_terminal_or_configuration_is_refused(tmp_path):
    feeder = example_feeder()
    end = feeder.add(cim.TransformerTankEnd(mRID=feeder.mrid(), endNumber=1))
    with pytest.raises(
        ValueError,
        match=rf"TransformerTankEnd {end.mRID}: cim:TransformerEnd.Terminal has no "
        "ConductingEquipment",
    ):
        describe_feeder(feeder, tmp_path)


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
    with feeder.frame("substation"):
        feeder.transformer("hv", "bus", 115.0, 12.47, WC.D, WC.Yn, tap_changer=True)
    feeder.line("head", "n1", 1.0)
    record = describe_feeder(feeder, tmp_path)
    assert record["gk:substationLTC"] is True
    assert record["gk:regulatorCount"] == 0
    assert record["gk:hvConnection"] == "gk:Connection.Delta"
    assert record["gk:mvConnection"] == "gk:Connection.WyeGrounded"


def two_bank_station(feeder: FeederBuilder, ltc_on: str | None = None, tie_open=True):
    """A two-bus station (contract 3.5 rule 6): a Delta-WyeGrounded bank on "bus", which feeds
    this feeder, and a WyeGrounded-WyeGrounded bank on "bus_1", which feeds a sibling, joined by
    a bus tie. `ltc_on` puts an LTC on one bank's transformer, or a regulator bank between that
    transformer and its bus."""
    feeder.source("hv", kv=69.0)
    with feeder.frame("substation"):
        for bus, side, high in (("bus", "own", WC.D), ("bus_1", "other", WC.Yn)):
            low = f"{bus}_regulated" if ltc_on == f"{side} regulator" else bus
            ltc = ltc_on == f"{side} transformer"
            feeder.transformer("hv", low, 69.0, 12.47, high, WC.Yn, tap_changer=ltc)
            if low != bus:
                for phase in (cim.SinglePhaseKind.A, cim.SinglePhaseKind.B, cim.SinglePhaseKind.C):
                    feeder.regulator(low, bus, phase)
        feeder.breaker("sibling_head", bus="bus_1")
        feeder.switch(cim.Disconnector, "bus", "bus_1", normalOpen=tie_open)
    feeder.line("head", "n1", 1.0)


@pytest.mark.parametrize(
    "ltc_on, expected",
    [
        (None, False),
        ("own transformer", True),
        ("own regulator", True),
        ("other transformer", False),
        ("other regulator", False),
    ],
)
def test_two_bank_station_uses_the_bank_that_feeds_the_feeder(tmp_path, ltc_on, expected):
    """contract 4.5a: the transformer whose bus feeds the feeder in the normal state."""
    feeder = FeederBuilder()
    two_bank_station(feeder, ltc_on)
    record = describe_feeder(feeder, tmp_path)
    assert record["gk:hvConnection"] == "gk:Connection.Delta"
    assert record["gk:mvConnection"] == "gk:Connection.WyeGrounded"
    assert record["gk:substationLTC"] is expected
    assert record["gk:regulatorCount"] == 0


def test_closed_bus_tie_joins_both_banks(tmp_path):
    feeder = FeederBuilder()
    two_bank_station(feeder, "other transformer", tie_open=False)
    record = describe_feeder(feeder, tmp_path)
    assert record["gk:hvConnection"] == "gk:Connection.Delta"  # equal counts go to scheme order
    assert record["gk:substationLTC"] is True


def test_no_bank_feeding_the_feeder_is_refused(tmp_path):
    feeder = FeederBuilder()
    feeder.source("hv", kv=69.0)
    with feeder.frame("substation"):
        feeder.transformer("hv", "bus_1", 69.0, 12.47, WC.D, WC.Yn)
    feeder.line("head", "n1", 1.0)
    with pytest.raises(
        ValueError,
        match=r"substation_VT-5e6f7a8b9c\.jsonld: no substation transformer feeds the feeder's "
        r"head node in the normal state",
    ):
        describe_feeder(feeder, tmp_path)


def test_without_substation_transformer_mv_is_the_source_connection(tmp_path):
    feeder = FeederBuilder()
    feeder.source("bus", grounded=False)
    feeder.line("head", "n1", 1.0)
    record = describe_feeder(feeder, tmp_path)
    assert "gk:hvConnection" not in record
    assert record["gk:mvConnection"] == "gk:Connection.Wye"


@pytest.mark.parametrize("grounded, expected", [(False, "Wye"), (True, "WyeGrounded")])
def test_two_source_station_uses_the_source_on_the_feeding_bus(tmp_path, grounded, expected):
    """contract 4.5a: without a substation transformer, the EnergySource on the bus that feeds
    the feeder; the other bus, behind a normally open bus tie, has the other grounding."""
    feeder = FeederBuilder()
    feeder.source("bus", grounded=grounded)
    feeder.source("bus_1", grounded=not grounded)
    with feeder.frame("substation"):
        feeder.breaker("sibling_head", bus="bus_1")
        feeder.switch(cim.Disconnector, "bus", "bus_1", normalOpen=True)
    feeder.line("head", "n1", 1.0)
    record = describe_feeder(feeder, tmp_path)
    assert "gk:hvConnection" not in record
    assert record["gk:mvConnection"] == f"gk:Connection.{expected}"


def test_no_source_feeding_the_feeder_is_refused(tmp_path):
    feeder = FeederBuilder()
    feeder.source("bus_1")
    feeder.line("head", "n1", 1.0)
    with pytest.raises(
        ValueError,
        match=r"substation_VT-5e6f7a8b9c\.jsonld: no EnergySource feeds the feeder's head node",
    ):
        describe_feeder(feeder, tmp_path)


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
    feeder.line("head", "n1", 1.0)
    head = feeder.feeder.NormalHeadTerminal.pop()
    head.NormalHeadFeeder = None
    with pytest.raises(
        ValueError, match=r"feeder_VT-0a1b2c3d4e\.jsonld: cim:Feeder\.NormalHeadTerminal"
    ):
        describe_feeder(feeder, tmp_path)


def test_head_terminal_is_the_first_feeder_equipment(tmp_path):
    """Not the station breaker, which is in the substation frame (contract 3.5)."""
    feeder = FeederBuilder()
    feeder.line("head", "n1", 1.0)
    (breaker,) = [obj for obj in feeder.models["substation"] if isinstance(obj, cim.Breaker)]
    feeder.feeder.NormalHeadTerminal.pop().NormalHeadFeeder = None
    breaker.Terminals[1].NormalHeadFeeder = feeder.feeder
    feeder.feeder.NormalHeadTerminal.append(breaker.Terminals[1])
    with pytest.raises(ValueError, match=r"head Terminal .*Breaker .* is not in the feeder frame"):
        describe_feeder(feeder, tmp_path)


def test_station_regulator_is_the_substation_ltc_not_a_regulator(tmp_path):
    """A regulator shared by the station's feeders is in the substation frame (contract 3.5)."""
    feeder = FeederBuilder()
    feeder.source("source")
    with feeder.frame("substation"):
        for phase in (cim.SinglePhaseKind.A, cim.SinglePhaseKind.B, cim.SinglePhaseKind.C):
            feeder.regulator("source", "bus", phase)
    feeder.line("head", "n1", 1.0)
    record = describe_feeder(feeder, tmp_path)
    assert record["gk:substationLTC"] is True
    assert record["gk:regulatorCount"] == 0


def test_station_transformer_in_the_feeder_frame_is_refused(tmp_path):
    feeder = FeederBuilder()
    feeder.line("head", "n1", 1.0)
    feeder.transformer("n1", "n2", 69.0, 12.47, WC.D, WC.Yn)
    with pytest.raises(
        ValueError, match=r"feeder_VT-0a1b2c3d4e\.jsonld: PowerTransformer .*above"
    ):
        describe_feeder(feeder, tmp_path)


def test_segment_without_length_names_file_and_field(tmp_path):
    feeder = FeederBuilder()
    feeder.line("head", "n1", 1.0).length = None
    with pytest.raises(ValueError, match=r"\.jsonld: ACLineSegment .*cim:Conductor\.length"):
        describe_feeder(feeder, tmp_path)


def test_missing_jsonld_directory(tmp_path):
    with pytest.raises(ValueError, match=r"jsonld: directory is missing"):
        structural_properties(tmp_path / "jsonld", MODEL_ID)


def test_missing_feeder_frame(tmp_path):
    jsonld_dir = FeederBuilder().write(tmp_path / "jsonld")
    (jsonld_dir / f"feeder_{MODEL_ID}.jsonld").unlink()
    with pytest.raises(ValueError, match=r"feeder_VT-0a1b2c3d4e\.jsonld: file is missing"):
        structural_properties(jsonld_dir, MODEL_ID)


def test_missing_area_frame(tmp_path):
    jsonld_dir = FeederBuilder().write(tmp_path / "jsonld")
    (jsonld_dir / "area.jsonld").unlink()
    with pytest.raises(ValueError, match=r"area\.jsonld: file is missing \(the area frame\)"):
        structural_properties(jsonld_dir, MODEL_ID)


def test_feeder_outside_the_area_frame_is_refused(tmp_path):
    """The Feeder is in the area frame, not the feeder frame (contract 3.5, 0.5.0)."""
    feeder = FeederBuilder()
    feeder.line("head", "n1", 1.0)
    feeder.models["area"].remove(feeder.feeder)
    feeder.add(feeder.feeder, "feeder")
    with pytest.raises(
        ValueError,
        match=r"area\.jsonld: 0 cim:Feeder objects contain the equipment of "
        r"feeder_VT-0a1b2c3d4e\.jsonld; expected exactly 1",
    ):
        describe_feeder(feeder, tmp_path)


def test_feeder_frame_in_two_feeders_is_refused(tmp_path):
    feeder = FeederBuilder()
    feeder.line("head", "n1", 1.0)
    other = feeder.add(cim.Feeder(mRID=feeder.mrid()), "area")
    feeder.line("n1", "n2", 1.0).EquipmentContainer = other
    with pytest.raises(ValueError, match=r"area\.jsonld: 2 cim:Feeder objects contain"):
        describe_feeder(feeder, tmp_path)


def test_one_substation_frame(tmp_path):
    feeder = FeederBuilder()
    feeder.line("head", "n1", 1.0)
    jsonld_dir = feeder.write(tmp_path / "jsonld")
    (jsonld_dir / "substation_VT-5e6f7a8b9c.jsonld").rename(jsonld_dir / "substation_a.jsonld")
    (jsonld_dir / "substation_b.jsonld").write_text((jsonld_dir / "boundary.jsonld").read_text())
    with pytest.raises(
        ValueError, match=r"holds 2 substation_\*\.jsonld files; expected exactly 1"
    ):
        structural_properties(jsonld_dir, MODEL_ID)


def ieee13_models(network: NodeBreakerModel) -> dict[str, list]:
    """IEEE 13 split into frames (contract 3.5): the Substation, the source, the substation
    transformer and the breaker, with their base voltages, in the substation frame; the
    breaker's feeder-side node "brkr" as the head node in the boundary; the Feeder and the
    restated Substation in the area frame; and the rest in the feeder frame."""
    by_name = {
        obj.name: obj
        for cim_class in (cim.EnergySource, cim.PowerTransformer, cim.Breaker)
        for obj in network.graph[cim_class].values()
    }
    station = [by_name["source"], by_name["sub3"], by_name["brkr1"]]
    ends = list(by_name["sub3"].PowerTransformerEnd)
    substations = list(network.graph[cim.Substation].values())
    substation = [*substations, *station, *ends]
    substation += [obj.BaseVoltage for obj in [*station, *ends] if obj.BaseVoltage is not None]
    for equipment in station:
        for terminal in equipment.Terminals:
            substation += [terminal, terminal.ConnectivityNode]
    head = next(
        t.ConnectivityNode for t in by_name["brkr1"].Terminals if t.ConnectivityNode.name == "brkr"
    )
    substation.remove(head)
    models = {
        "area": [*substations, *network.graph[cim.Feeder].values()],
        "substation": list(dict.fromkeys(substation)),
        "boundary": [head],
    }
    placed = {obj.identifier for objs in models.values() for obj in objs}
    models["feeder"] = [
        obj
        for by_id in network.graph.values()
        for obj in by_id.values()
        if obj.identifier not in placed or isinstance(obj, cim.BaseVoltage)
    ]
    return models


def test_ieee13(tmp_path):
    """IEEE 13 (CIMHub CIM XML) split into frames, with the regulator's terminal on the head
    node as the feeder head, which the CIM XML does not set."""
    use_profile()
    network = NodeBreakerModel(
        container=None, connection=XMLFile(str(IEEE13_XML)), distributed=False
    )
    (feeder,) = network.graph[cim.Feeder].values()
    (regulator,) = [
        obj for obj in network.graph[cim.PowerTransformer].values() if obj.name == "Reg"
    ]
    head = next(t for t in regulator.Terminals if t.ConnectivityNode.name == "brkr")
    head.NormalHeadFeeder = feeder
    feeder.NormalHeadTerminal.append(head)
    jsonld_dir = write_models(tmp_path / "jsonld", ieee13_models(network))
    record = structural_properties(jsonld_dir, MODEL_ID)
    assert record["gk:primaryVoltage"] == 4.16
    assert record["gk:voltageClass"] == 5
    assert record["gk:feederLength"] == 2.499  # 8,200 ft of line at 4.16 kV
    assert record["gk:undergroundShare"] is None  # impedances only, no wire data
    assert record["gk:hvConnection"] == "gk:Connection.Delta"
    assert record["gk:mvConnection"] == "gk:Connection.WyeGrounded"
    # The profile has no TransformerEndInfo.connectionKind, so the center-tapped tank's
    # secondary connection is unknown.
    assert record["gk:lvConnection"] is None
    # The three single-phase regulator tanks on the head node are one bank, at the feeder head.
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
