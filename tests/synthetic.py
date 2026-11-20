"""Synthetic feeder packages for the tests: tiny CIM networks written by CIM-Graph, split into
the per-model files of a contract 0.6.0 package (3.5) as a pipeline writes them (cim18v17, SI
convention, no header). They hold no real utility data."""

import json
import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID

import cimprofiles.cim18.cim18v17 as cim
from cimgraph.core import get_cim_profile
from cimgraph.models import NodeBreakerModel
from cimgraph.utils import write_json_ld

CONTRACT_DIR = Path(__file__).parent / "data" / "contract"
MODEL_ID = "VT-0a1b2c3d4e"
SIBLING_GROUP = "VT-5e6f7a8b9c"
# jsonld/ file stem of each model; the feeder frame also has an SSH (contract 3.5).
MODEL_FILES = {
    "area": "area",
    "boundary": "boundary",
    "substation": f"substation_{SIBLING_GROUP}",
    "feeder": f"feeder_{MODEL_ID}",
}
SSH_FILES = {"feeder": f"ssh_{MODEL_ID}"}
# The situation data of the feeder SSH (contract 3.5 rule 9).
SSH_ATTRIBUTES = {"p", "q"}
AUTHORITY = "https://gridkitchen.pnnl.gov/authority/test"
WGS84 = "urn:ogc:def:crs:OGC:1.3:CRS84"


def use_profile() -> None:
    os.environ["CIMG_CIM_PROFILE"] = "cim18v17"
    os.environ["CIMG_USE_UNITS"] = "true"
    os.environ["CIMG_MODEL_AUTHORITY"] = AUTHORITY
    os.environ["CIMG_MODEL_NAME"] = ""
    get_cim_profile.cache_clear()


class FeederBuilder:
    """A package's models (contract 3.5). The substation frame declares the Substation and has a
    breaker from its bus, node "bus", to the head node "head", which is in the boundary. The area
    frame holds the Feeder and restates the Substation. Objects go to the feeder frame unless
    added inside `frame()`; each frame declares the base voltages it uses. The feeder's
    NormalHeadTerminal is the terminal, on "head", of its first equipment there."""

    def __init__(self, primary_kv: float = 12.47):
        use_profile()
        self.count = 0
        self.models = {model: [] for model in MODEL_FILES}
        self.model = "feeder"
        self.base_voltages = {}
        self.nodes = {}
        self.primary_kv = primary_kv
        self.substation = self.add(cim.Substation(mRID=self.mrid()), "substation")
        self.add(self.substation, "area")
        self.feeder = self.add(
            cim.Feeder(
                mRID=self.mrid(), name="feeder", NormalEnergizingSubstation=self.substation
            ),
            "area",
        )
        with self.frame("substation"):
            self.breaker("head")

    def mrid(self) -> str:
        self.count += 1
        return str(UUID(int=self.count))

    def add(self, obj, model: str | None = None):
        """Declares the object in a model; a second declaration restates it (contract 3.5)."""
        objects = self.models[model or self.model]
        if obj not in objects:
            objects.append(obj)
        return obj

    @contextmanager
    def frame(self, model: str):
        """Objects added inside go to that model."""
        self.model = model
        try:
            yield
        finally:
            self.model = "feeder"

    def container(self):
        return {"substation": self.substation, "feeder": self.feeder}.get(self.model)

    def base_voltage(self, kv: float):
        if kv not in self.base_voltages:
            self.base_voltages[kv] = cim.BaseVoltage(
                mRID=self.mrid(), nominalVoltage=cim.Voltage(kv, "kV")
            )
        return self.add(self.base_voltages[kv])

    def node(self, name: str, model: str | None = None):
        if name not in self.nodes:
            model = "boundary" if name == "head" else model
            self.nodes[name] = self.add(cim.ConnectivityNode(mRID=self.mrid(), name=name), model)
        return self.nodes[name]

    def breaker(self, head_node: str, bus: str = "bus"):
        """A station breaker from a bus to a feeder's head node, a boundary node."""
        self.node(head_node, "boundary")
        breaker = self.switch(cim.Breaker, bus, head_node, areaBoundary=True)
        breaker.EquipmentContainer = self.substation
        return breaker

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
        if node_name == "head" and self.model == "feeder" and not self.feeder.NormalHeadTerminal:
            terminal.NormalHeadFeeder = self.feeder
            self.feeder.NormalHeadTerminal.append(terminal)
        return terminal

    def equipment(self, cim_class, nodes: list[str], kv: float | None = None, **attributes):
        kv = self.primary_kv if kv is None else kv
        equipment = self.add(
            cim_class(
                mRID=self.mrid(),
                BaseVoltage=self.base_voltage(kv),
                EquipmentContainer=self.container(),
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
            cim.PowerTransformer(mRID=self.mrid(), EquipmentContainer=self.container())
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
        """The EnergySource, always in the substation frame."""
        with self.frame("substation"):
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

    def area(self, own_node: str, siblings: int = 2):
        """What a package of a tied distribution area carries (contract 3.5, 0.6.0).

        - area frame: every ConnectedArea of the area, from the restated transmission area to
          three feeder areas; a Feeder per sibling and one of the other substation, which is
          restated; and the normally open tie from `own_node` to "far", contained by the
          distribution area;
        - substation frame: a breaker per sibling feeder, ending at its head node;
        - boundary: the sibling head nodes and both sides of the tie. The other feeder's segment,
          in its own package, ends on "far", so here the node has only the tie's terminal.
        """
        area_kind = cim.ConnectedAreaKind
        with self.frame("area"):
            transmission = self.add(
                cim.ConnectedArea(mRID=self.mrid(), kind=area_kind.transmissionArea)
            )
            distribution = self.add(
                cim.ConnectedArea(
                    mRID=self.mrid(),
                    kind=area_kind.distributionArea,
                    ContainedWithin=transmission,
                )
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
            other = self.add(cim.Substation(mRID=self.mrid()))
            for substation in [self.substation] * siblings + [other]:
                self.add(cim.Feeder(mRID=self.mrid(), NormalEnergizingSubstation=substation))
        with self.frame("substation"):
            for sibling in range(siblings):
                self.breaker(f"sibling_head_{sibling}")
        own = self.nodes[own_node]
        self.models["feeder"].remove(own)
        self.add(own, "boundary")
        for node in (own, self.node("far", "boundary")):
            node.ConnectivityNodeContainer = distribution
        with self.frame("area"):
            tie = self.switch(
                cim.LoadBreakSwitch, own_node, "far", normalOpen=True, areaBoundary=True, open=True
            )
        tie.EquipmentContainer = distribution
        return tie

    def write(self, jsonld_dir: Path) -> Path:
        return write_models(jsonld_dir, self.models)


def _document(objects: list) -> dict:
    """The JSON-LD of some objects, without the dataset header CIM-Graph writes: as a per-model
    file of a package (contract 5.2)."""
    network = NodeBreakerModel(container=None, connection=None, distributed=False)
    for obj in objects:
        network.add_to_graph(obj)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "model.jsonld"
        write_json_ld(network, str(path), convention="si")
        document = json.loads(path.read_text())
    return {"@context": document["@context"], "@graph": document["@graph"]}


def _split_situation(graph: list) -> list:
    """Moves the SSH attributes out of a frame's rows, returning the SSH's Update rows."""
    updates = []
    for item in graph:
        situation = {
            key: value for key, value in item.items() if key.rsplit(".", 1)[-1] in SSH_ATTRIBUTES
        }
        if situation:
            updates.append({"@id": item["@id"], "@type": item["@type"], **situation})
            for key in situation:
                del item[key]
    return updates


def write_models(jsonld_dir: Path, models: dict[str, list]) -> Path:
    """jsonld/ of a package: one file per model of MODEL_FILES, and an SSH per frame."""
    jsonld_dir.mkdir(parents=True, exist_ok=True)
    for model, stem in MODEL_FILES.items():
        document = _document(models.get(model, []))
        if model in SSH_FILES:
            ssh = {
                "@context": document["@context"],
                "@graph": _split_situation(document["@graph"]),
            }
            (jsonld_dir / f"{SSH_FILES[model]}.jsonld").write_text(json.dumps(ssh, indent=4))
        (jsonld_dir / f"{stem}.jsonld").write_text(json.dumps(document, indent=4))
    return jsonld_dir


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
    feeder.write(package / "jsonld")
    return package
