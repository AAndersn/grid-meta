"""Synthetic feeder packages for the tests: tiny CIM networks written by CIM-Graph, as a pipeline
writes them (cim18v17, SI convention). They hold no real utility data."""

import json
import os
import shutil
from pathlib import Path
from uuid import UUID

import cimprofiles.cim18.cim18v17 as cim
from cimgraph.core import get_cim_profile
from cimgraph.models import FeederModel
from cimgraph.utils import write_json_ld

CONTRACT_DIR = Path(__file__).parent / "data" / "contract"
MODEL_ID = "VT-0a1b2c3d4e"
AUTHORITY = "https://gridkitchen.pnnl.gov/authority/test"
WGS84 = "urn:ogc:def:crs:OGC:1.3:CRS84"


def use_profile() -> None:
    os.environ["CIMG_CIM_PROFILE"] = "cim18v17"
    os.environ["CIMG_USE_UNITS"] = "true"
    os.environ["CIMG_MODEL_AUTHORITY"] = AUTHORITY
    os.environ["CIMG_MODEL_NAME"] = ""
    get_cim_profile.cache_clear()


class FeederBuilder:
    """A feeder whose head is a breaker from node "bus" to node "head" at the primary voltage."""

    def __init__(self, primary_kv: float = 12.47):
        use_profile()
        self.count = 0
        self.feeder = cim.Feeder(mRID=self.mrid(), name="feeder")
        self.network = FeederModel(container=self.feeder, connection=None, distributed=False)
        self.network.add_to_graph(self.feeder)
        self.base_voltages = {}
        self.nodes = {}
        self.primary_kv = primary_kv
        head = self.switch(cim.Breaker, "bus", "head")
        head.Terminals[0].NormalHeadFeeder = self.feeder
        self.feeder.NormalHeadTerminal.append(head.Terminals[0])

    def mrid(self) -> str:
        self.count += 1
        return str(UUID(int=self.count))

    def add(self, obj):
        self.network.add_to_graph(obj)
        return obj

    def base_voltage(self, kv: float):
        if kv not in self.base_voltages:
            self.base_voltages[kv] = self.add(
                cim.BaseVoltage(mRID=self.mrid(), nominalVoltage=cim.Voltage(kv, "kV"))
            )
        return self.base_voltages[kv]

    def node(self, name: str):
        if name not in self.nodes:
            self.nodes[name] = self.add(cim.ConnectivityNode(mRID=self.mrid(), name=name))
        return self.nodes[name]

    def terminal(self, equipment, node_name: str, phases=None):
        node = self.node(node_name)
        terminal = self.add(
            cim.Terminal(
                mRID=self.mrid(),
                ConductingEquipment=equipment,
                ConnectivityNode=node,
                sequenceNumber=len(equipment.Terminals) + 1,
                phases=phases,
            )
        )
        equipment.Terminals.append(terminal)
        node.Terminals.append(terminal)
        return terminal

    def equipment(self, cim_class, nodes: list[str], kv: float | None = None, **attributes):
        kv = self.primary_kv if kv is None else kv
        equipment = self.add(
            cim_class(
                mRID=self.mrid(),
                BaseVoltage=self.base_voltage(kv),
                EquipmentContainer=self.feeder,
                **attributes,
            )
        )
        for node_name in nodes:
            self.terminal(equipment, node_name)
        return equipment

    def switch(self, cim_class, node1: str, node2: str, kv: float | None = None, **attributes):
        return self.equipment(cim_class, [node1, node2], kv, **attributes)

    def line(self, node1: str, node2: str, km: float, kv: float | None = None, wire=None):
        line = self.equipment(cim.ACLineSegment, [node1, node2], kv, length=cim.Length(km, "km"))
        if wire is not None:
            line.AssetDatasheet = self.add(wire(mRID=self.mrid()))
        return line

    def load(
        self, node: str, kw: float | None, kv: float | None = None, customers: int | None = 1
    ):
        power = None if kw is None else cim.ActivePower(kw, "kW")
        return self.equipment(cim.EnergyConsumer, [node], kv, p=power, customerCount=customers)

    def transformer(
        self,
        node1: str,
        node2: str,
        kv1: float,
        kv2: float,
        connection1,
        connection2,
        grounded2: bool = True,
        phases2=None,
        tap_changer=False,
    ):
        transformer = self.add(
            cim.PowerTransformer(mRID=self.mrid(), EquipmentContainer=self.feeder)
        )
        for number, node, kv, connection, grounded, phases in (
            (1, node1, kv1, connection1, True, None),
            (2, node2, kv2, connection2, grounded2, phases2),
        ):
            end = self.add(
                cim.PowerTransformerEnd(
                    mRID=self.mrid(),
                    endNumber=number,
                    PowerTransformer=transformer,
                    connectionKind=connection,
                    grounded=grounded,
                    BaseVoltage=self.base_voltage(kv),
                    Terminal=self.terminal(transformer, node, phases),
                )
            )
            transformer.PowerTransformerEnd.append(end)
            if tap_changer and number == 2:
                self.add(cim.RatioTapChanger(mRID=self.mrid(), TransformerEnd=end, ltcFlag=True))
        return transformer

    def center_tap(self, node1: str, node2: str, kva: float = 25.0):
        return self.transformer(
            node1,
            node2,
            self.primary_kv,
            0.24,
            cim.WindingConnection.Y,
            cim.WindingConnection.I,
            phases2=cim.PhaseCode.s12N,
        )

    def regulator(self, node1: str, node2: str, phase):
        """One single-phase VoltageRegulator, as vec_cim writes one per phase."""
        unit = self.equipment(cim.VoltageRegulator, [], None)
        for number, node in ((1, node1), (2, node2)):
            end = self.add(
                cim.AutoTransformerEnd(
                    mRID=self.mrid(),
                    endNumber=number,
                    AutoTransformer=unit,
                    phase=phase,
                    BaseVoltage=self.base_voltage(self.primary_kv),
                    Terminal=self.terminal(unit, node),
                )
            )
            unit.AutoTransformerEnd.append(end)
            if number == 2:
                self.add(cim.RatioTapChanger(mRID=self.mrid(), TransformerEnd=end, ltcFlag=True))
        return unit

    def capacitor(self, node: str):
        return self.equipment(
            cim.LinearShuntCompensator, [node], None, nomQ=cim.ReactivePower(300, "kVAr")
        )

    def generator(self, node: str, kva: float | None, kv: float = 0.24):
        rating = None if kva is None else cim.ApparentPower(kva, "kVA")
        return self.equipment(cim.PowerElectronicsConnection, [node], kv, ratedS=rating)

    def source(self, node: str, kv: float | None = None, grounded: bool | None = None):
        return self.equipment(cim.EnergySource, [node], kv, grounded=grounded)

    def position(self, crs_urn: str | None, x: float = -72.5, y: float = 44.2):
        crs = None
        if crs_urn is not None:
            crs = self.add(cim.CoordinateSystem(mRID=self.mrid(), crsUrn=crs_urn))
        location = self.add(cim.Location(mRID=self.mrid(), CoordinateSystem=crs))
        self.add(
            cim.PositionPoint(
                Location=location, xPosition=str(x), yPosition=str(y), sequenceNumber=1
            )
        )

    def owned_tie(self, own_node: str):
        """What a feeder that owns a tie carries (contract 3.5, 0.3.0): from areas.cimtbl, the
        distribution area's ConnectedAreas, including those of two other feeders; from
        boundary_<set>.cimtbl, the boundary node "far" in that area; and in its own parts, the
        normally open tie switch from `own_node` to "far". The other feeder's segment, in its own
        package, ends on "far", so here the node has only the tie's terminal."""
        area_kind = cim.ConnectedAreaKind
        distribution = self.add(
            cim.ConnectedArea(mRID=self.mrid(), kind=area_kind.distributionArea)
        )
        service = self.add(
            cim.ConnectedArea(
                mRID=self.mrid(),
                kind=area_kind.substationServiceArea,
                ContainedWithin=distribution,
            )
        )
        for _feeder in range(3):
            self.add(
                cim.ConnectedArea(
                    mRID=self.mrid(), kind=area_kind.feederArea, ContainedWithin=service
                )
            )
        far = self.node("far")
        far.ConnectivityNodeContainer = distribution
        far.BaseVoltage = self.base_voltage(self.primary_kv)
        return self.switch(
            cim.LoadBreakSwitch, own_node, "far", normalOpen=True, areaBoundary=True
        )

    def write(self, path: Path) -> Path:
        write_json_ld(self.network, str(path), convention="si", header={"dct:title": path.stem})
        return path


def example_feeder() -> FeederBuilder:
    """A small feeder with one of everything: 2.5 km of primary, a fifth underground."""
    feeder = FeederBuilder()
    feeder.source("bus")
    feeder.line("head", "n1", 2.0, wire=cim.OverheadWireInfo)
    feeder.line("n1", "n2", 0.5, wire=cim.ConcentricNeutralCableInfo)
    feeder.center_tap("n1", "s1")
    feeder.center_tap("n2", "s2")
    feeder.load("s1", 2.0, kv=0.24)
    feeder.load("s1", 3.0, kv=0.24)
    feeder.load("s2", 12.0, kv=0.24)
    feeder.generator("s2", 7.6)
    feeder.switch(cim.Fuse, "n1", "f1")
    feeder.switch(cim.Recloser, "n2", "r1")
    feeder.capacitor("n2")
    feeder.position(WGS84)
    return feeder


def write_json(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data, indent=2))
    return path


def write_package(
    root: Path, feeder: FeederBuilder, service_points: str, sanitize: dict | None = None
) -> Path:
    """A feeder package (interface A) with the contract's example source, provenance and verify
    files."""
    package = root / MODEL_ID
    (package / "private").mkdir(parents=True)
    for name in ("source.json", "provenance.json", "verify.json"):
        shutil.copy(CONTRACT_DIR / name, package / name)
    (package / "private" / "service_points.csv").write_text(service_points)
    if sanitize is not None:
        write_json(package / "sanitize.json", sanitize)
    feeder.write(package / f"{MODEL_ID}.jsonld")
    return package
