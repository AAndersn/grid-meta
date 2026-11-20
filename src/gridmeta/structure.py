"""Structural feeder record properties from the package's CIM models (contract 3.5 and 4.2).

Every file in the package's jsonld/ directory (the area frame, the boundary, the substation and
feeder frames and the feeder SSH) is read into one graph with CIM-Graph's JSONLDFile, in the
cim18v17 profile, so references resolve and the SSH's p and q reach their objects. An object that
several files declare (restated reference data and containers) is one object of the graph. The
package's feeder is the one Feeder of the area frame that contains the feeder frame's equipment.
Counts and properties come from the objects the feeder frame declares. The substation frame gives
only the SubstationSource facts and the substation LTC. The area frame's ties and other feeders'
breakers are counted in neither. Every quantity goes through CIMUnit `.to()`. A property whose
value is unknown is left out; a missing or invalid input raises ValueError naming the file and
the field.

Equipment roles, by frame and by the nominal voltages of a transformer's ends:
- substation transformer: a substation-frame PowerTransformer with an end above the primary
  voltage. The feeding transformers are those on the bus that feeds the feeder's head node in the
  normal state;
- regulator unit: a PowerTransformer whose ends all have one voltage and which has a
  RatioTapChanger, or an AutoTransformer (VoltageRegulator) with a RatioTapChanger. In the
  substation frame it is a station regulator, of one bus or shared by several feeders;
- distribution transformer: every other feeder-frame PowerTransformer.

gk:evCount is never written: nothing in a package says that the source has EV data.
"""

import logging
import os
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import cimprofiles.cim18.cim18v17 as cim
from cimgraph.databases import JSONLDFile, reference_key
from cimgraph.models import NodeBreakerModel

from gridmeta.package import read_json
from gridmeta.rounding import largest_remainder_shares, round_share

PROFILE = "cim18v17"
VOLTAGE_CLASSES_KV = (5, 15, 25, 35)
SIZE_BIN_EDGES = (0, 5, 50, 500, 5000)
CONNECTION_ORDER = (
    "Delta",
    "Wye",
    "WyeGrounded",
    "CenterTap",
    "OpenDelta",
    "OpenWye",
    "Zigzag",
    "SinglePhase",
)
NO_POSITIONS = "gk:GeographicSpecificity.None"
WINDING_CONNECTIONS = {
    cim.WindingConnection.D: "Delta",
    cim.WindingConnection.Yn: "WyeGrounded",
    cim.WindingConnection.oD: "OpenDelta",
    cim.WindingConnection.oY: "OpenWye",
    cim.WindingConnection.Z: "Zigzag",
    cim.WindingConnection.Zn: "Zigzag",
}
SPLIT_PHASES = {
    cim.PhaseCode.s1,
    cim.PhaseCode.s2,
    cim.PhaseCode.s12,
    cim.PhaseCode.s1N,
    cim.PhaseCode.s2N,
    cim.PhaseCode.s12N,
}
# contract 3 and 13a.1: WGS84 is EPSG:4326 or OGC CRS84 (the CRS the pipelines write).
WGS84_CRS = {
    "epsg:4326",
    "urn:ogc:def:crs:epsg::4326",
    "http://www.opengis.net/def/crs/epsg/0/4326",
    "crs84",
    "ogc:crs84",
    "urn:ogc:def:crs:ogc:1.3:crs84",
    "http://www.opengis.net/def/crs/ogc/1.3/crs84",
}

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Frame:
    """One frame model of the package (contract 3.5): its file and the objects it declares."""

    path: Path
    identifiers: frozenset

    def holds(self, obj) -> bool:
        return obj.identifier in self.identifiers


def _declared(connection: JSONLDFile, document: dict) -> frozenset:
    """The identifiers of the objects a model file declares; rows of classes outside the profile
    are skipped, as the reader skips them."""
    identifiers = set()
    for item in document.get("@graph", []):
        obj = connection.object_index.get(reference_key(item.get("@id", "")))
        if obj is not None:
            identifiers.add(obj.identifier)
    return frozenset(identifiers)


def read_models(jsonld_dir: Path, model_id: str) -> tuple[NodeBreakerModel, Frame, Frame, Frame]:
    """Every model in jsonld/, in one graph, with the feeder frame (feeder_<model_id>.jsonld),
    the substation frame (the one substation_*.jsonld) and the area frame (area.jsonld). Sets
    CIM-Graph's settings process-wide, as it reads them from the environment: the profile, units,
    and no fetching of contexts (the files' context must be in the cim-profiles offline cache, so
    describing a package makes no request)."""
    if not jsonld_dir.is_dir():
        raise ValueError(f"{jsonld_dir}: directory is missing")
    paths = sorted(jsonld_dir.glob("*.jsonld"))
    documents = {path: read_json(path) for path in paths}
    feeder_path = jsonld_dir / f"feeder_{model_id}.jsonld"
    area_path = jsonld_dir / "area.jsonld"
    for path, frame in ((feeder_path, "the feeder frame"), (area_path, "the area frame")):
        if path not in documents:
            raise ValueError(f"{path}: file is missing ({frame})")
    substation_paths = [path for path in paths if path.name.startswith("substation_")]
    if len(substation_paths) != 1:
        raise ValueError(
            f"{jsonld_dir}: holds {len(substation_paths)} substation_*.jsonld files; expected "
            "exactly 1 (the substation frame)"
        )
    (substation_path,) = substation_paths
    os.environ["CIMG_CIM_PROFILE"] = PROFILE
    os.environ["CIMG_USE_UNITS"] = "true"
    os.environ["CIMG_ALLOW_REMOTE_CONTEXT"] = "false"
    connection = JSONLDFile([str(path) for path in paths])
    network = NodeBreakerModel(container=None, connection=connection, distributed=False)
    frames = [
        Frame(path, _declared(connection, documents[path]))
        for path in (feeder_path, substation_path, area_path)
    ]
    return network, *frames


def objects(network: NodeBreakerModel, cim_class: type, frame: Frame | None = None) -> list:
    """The objects of a class and its subclasses, in file order; only the frame's, if given."""
    return [
        obj
        for graph_class, by_id in network.graph.items()
        if issubclass(graph_class, cim_class)
        for obj in by_id.values()
        if frame is None or frame.holds(obj)
    ]


def _kilovolts(base_voltage) -> float:
    return round(base_voltage.nominalVoltage.to("kV"), 6)


def _equipment_kv(path: Path, equipment) -> float:
    if equipment.BaseVoltage is None or equipment.BaseVoltage.nominalVoltage is None:
        raise ValueError(
            f"{path}: {type(equipment).__name__} {equipment.mRID}: "
            "cim:ConductingEquipment.BaseVoltage is not set"
        )
    return _kilovolts(equipment.BaseVoltage)


def _end_kv(path: Path, end) -> float:
    if end.BaseVoltage is None or end.BaseVoltage.nominalVoltage is None:
        raise ValueError(
            f"{path}: {type(end).__name__} {end.mRID}: cim:TransformerEnd.BaseVoltage is not set"
        )
    return _kilovolts(end.BaseVoltage)


def _nodes(terminals) -> frozenset:
    return frozenset(
        terminal.ConnectivityNode.identifier
        for terminal in terminals
        if terminal is not None and terminal.ConnectivityNode is not None
    )


class Topology:
    """The feeder head and the transformer roles of one package's models."""

    def __init__(self, network: NodeBreakerModel, feeder: Frame, substation: Frame, area: Frame):
        self.network = network
        self.feeder = feeder
        self.substation = substation
        self.path = feeder.path
        path = feeder.path
        # contract 3 and 3.5 rule 7: the Feeder's NormalHeadTerminal is the terminal, on the head
        # node, of the feeder frame's first equipment.
        self.head_terminals = self._package_feeder(area).NormalHeadTerminal
        if not self.head_terminals:
            raise ValueError(f"{path}: cim:Feeder.NormalHeadTerminal is not set")
        self.ends = self._transformer_ends()
        head_kvs = set()
        for terminal in self.head_terminals:
            equipment = terminal.ConductingEquipment
            if equipment is None:
                raise ValueError(
                    f"{path}: head Terminal {terminal.mRID}: cim:Terminal.ConductingEquipment "
                    "is not set"
                )
            if not feeder.holds(equipment):
                raise ValueError(
                    f"{path}: head Terminal {terminal.mRID}: its {type(equipment).__name__} "
                    f"{equipment.mRID} is not in the feeder frame"
                )
            head_kvs.add(self._terminal_kv(terminal))
        if len(head_kvs) != 1:
            raise ValueError(
                f"{path}: the feeder head terminals have voltages {sorted(head_kvs)} kV"
            )
        self.primary_kv = head_kvs.pop()
        self.head_nodes = _nodes(self.head_terminals)

        self.substation_transformers = []
        self.distribution_transformers = []
        station_regulator_units = [
            unit
            for unit in self.substation_objects(cim.AutoTransformer)
            if self._has_tap_changer(unit)
        ]
        for transformer in self.substation_objects(cim.PowerTransformer):
            kvs = self._kvs(substation.path, transformer)
            if max(kvs) > self.primary_kv:
                self.substation_transformers.append(transformer)
            elif len(kvs) == 1 and self._has_tap_changer(transformer):
                station_regulator_units.append(transformer)
        self.feeding_transformers, self.bus_regulators, self.feeding_sources = self._feeding_bus(
            station_regulator_units
        )
        regulator_units = [
            unit
            for unit in self.feeder_objects(cim.AutoTransformer)
            if self._has_tap_changer(unit)
        ]
        for transformer in self.feeder_objects(cim.PowerTransformer):
            kvs = self._kvs(path, transformer)
            if max(kvs) > self.primary_kv:
                raise ValueError(
                    f"{path}: PowerTransformer {transformer.mRID} has an end above the primary "
                    f"voltage {self.primary_kv} kV; station transformers are in the substation "
                    "frame (contract 3.5)"
                )
            if len(kvs) == 1 and self._has_tap_changer(transformer):
                regulator_units.append(transformer)
            else:
                self.distribution_transformers.append(transformer)
        self.regulator_banks = self._banks(regulator_units)

    def _feeding_bus(self, regulator_units: list) -> tuple[list, list, list]:
        """The substation transformers, station regulators and EnergySources on the bus that
        feeds the head nodes in the normal state (contract 4.5a): nodes joined through the
        substation frame's closed equipment, across regulators but not substation transformers.
        The sources matter only in a station without substation transformers."""
        transformer_ids = {transformer.identifier for transformer in self.substation_transformers}
        station = [
            equipment
            for equipment in self.substation_objects(cim.ConductingEquipment)
            if equipment.identifier not in transformer_ids
        ]
        component_of = _component_finder(self, station)
        bus = {component_of(node) for node in self.head_nodes}

        def on_bus(equipment) -> bool:
            return any(component_of(node) in bus for node in self.terminal_nodes(equipment))

        transformers = [
            transformer for transformer in self.substation_transformers if on_bus(transformer)
        ]
        if self.substation_transformers and not transformers:
            raise ValueError(
                f"{self.substation.path}: no substation transformer feeds the feeder's head node "
                "in the normal state (contract 4.5a)"
            )
        station_sources = self.substation_objects(cim.EnergySource)
        sources = [source for source in station_sources if on_bus(source)]
        if not self.substation_transformers and station_sources and not sources:
            raise ValueError(
                f"{self.substation.path}: no EnergySource feeds the feeder's head node in the "
                "normal state (contract 4.5a)"
            )
        return transformers, [unit for unit in regulator_units if on_bus(unit)], sources

    def _package_feeder(self, area: Frame):
        """The one Feeder of the area frame that contains the feeder frame's equipment."""
        containers = {
            equipment.EquipmentContainer.identifier
            for equipment in self.feeder_objects(cim.Equipment)
            if equipment.EquipmentContainer is not None
        }
        feeders = [
            feeder
            for feeder in objects(self.network, cim.Feeder, area)
            if feeder.identifier in containers
        ]
        if len(feeders) != 1:
            raise ValueError(
                f"{area.path}: {len(feeders)} cim:Feeder objects contain the equipment of "
                f"{self.path.name}; expected exactly 1"
            )
        return feeders[0]

    def feeder_objects(self, cim_class: type) -> list:
        return objects(self.network, cim_class, self.feeder)

    def substation_objects(self, cim_class: type) -> list:
        return objects(self.network, cim_class, self.substation)

    def _terminal_kv(self, terminal) -> float:
        """The voltage of a terminal: its equipment's, or for a transformer, that of the end on
        the terminal."""
        equipment = terminal.ConductingEquipment
        ends = [end for end in self.ends.get(equipment.identifier, []) if end.Terminal is terminal]
        if equipment.BaseVoltage is None and ends:
            return _end_kv(self.path, ends[0])
        return _equipment_kv(self.path, equipment)

    def _kvs(self, path: Path, transformer) -> set:
        kvs = {_end_kv(path, end) for end in self.ends[transformer.identifier]}
        if not kvs:
            raise ValueError(f"{path}: PowerTransformer {transformer.mRID} has no ends")
        return kvs

    def _transformer_ends(self) -> dict:
        """Transformer identifier -> its ends. The profile has no TransformerTankEnd.TransformerTank,
        so a tank end belongs to the equipment of its Terminal. A tank end with a TankConfiguration
        and no Terminal is the template end of a TransformerTankConfiguration (CIMHub's GLM
        importer), not a tank's end, and is skipped."""
        ends = {
            transformer.identifier: list(transformer.PowerTransformerEnd)
            for transformer in objects(self.network, cim.PowerTransformer)
        }
        for unit in objects(self.network, cim.AutoTransformer):
            ends[unit.identifier] = list(unit.AutoTransformerEnd)
        for end in objects(self.network, cim.TransformerTankEnd):
            if end.Terminal is None and end.TankConfiguration is not None:
                continue
            if end.Terminal is None or end.Terminal.ConductingEquipment is None:
                raise ValueError(
                    f"{self.path}: TransformerTankEnd {end.mRID}: cim:TransformerEnd.Terminal "
                    "has no ConductingEquipment"
                )
            equipment = end.Terminal.ConductingEquipment
            if equipment.identifier not in ends:
                raise ValueError(
                    f"{self.path}: TransformerTankEnd {end.mRID}: its Terminal belongs to "
                    f"{type(equipment).__name__} {equipment.mRID}, not a transformer"
                )
            ends[equipment.identifier].append(end)
        for transformer_ends in ends.values():
            transformer_ends.sort(key=lambda end: end.endNumber or 0)
        return ends

    def _has_tap_changer(self, transformer) -> bool:
        return any(end.RatioTapChanger is not None for end in self.ends[transformer.identifier])

    def has_ltc(self, transformer) -> bool:
        """A tap changer with ltcFlag or a TapChangerControl (contract 4.5a)."""
        return any(
            end.RatioTapChanger is not None
            and (end.RatioTapChanger.ltcFlag or end.RatioTapChanger.TapChangerControl is not None)
            for end in self.ends[transformer.identifier]
        )

    def terminal_nodes(self, equipment) -> frozenset:
        """The connectivity nodes of the equipment's terminals and of its ends' terminals."""
        end_terminals = [end.Terminal for end in self.ends.get(equipment.identifier, [])]
        return _nodes([*equipment.Terminals, *end_terminals])

    def _banks(self, units: list) -> list[frozenset]:
        """Units that connect the same connectivity nodes form one bank (single-phase units of a
        three-phase bank, or one object per phase)."""
        # contract 4.5a
        return list(dict.fromkeys(self.terminal_nodes(unit) for unit in units))

    def connection(self, end) -> str | None:
        """The gk:Connection name of a transformer end; None when its connectionKind is not set
        or has no gk:Connection value (A, Dn, T)."""
        kind = end.connectionKind
        if kind == cim.WindingConnection.I:
            phases = end.Terminal.phases if end.Terminal is not None else None
            return "CenterTap" if phases in SPLIT_PHASES else "SinglePhase"
        if kind == cim.WindingConnection.Y:
            return "WyeGrounded" if end.grounded else "Wye"
        if kind is not None and kind not in WINDING_CONNECTIONS:
            _log.warning(
                "%s: %s %s: no gk:Connection for connectionKind %s; the connection is left out",
                self.path,
                type(end).__name__,
                end.mRID,
                kind,
            )
        return WINDING_CONNECTIONS.get(kind)


def most_common_connection(connections: list[str | None]) -> str | None:
    """The gk:Connection IRI of the most common connection, ties to the earlier one in scheme
    order. None when there are none, or when any connection is unknown (the most common one could
    be the unknown one)."""
    # contract 4.5a
    if not connections or None in connections:
        return None
    counts = Counter(connections)
    best = max(CONNECTION_ORDER, key=lambda name: (counts[name], -CONNECTION_ORDER.index(name)))
    return f"gk:Connection.{best}"


def voltage_class(primary_kv: float) -> int | None:
    """The smallest class at or above the primary voltage; None above 35 kV."""
    # contract 4.5a
    return next((kv for kv in VOLTAGE_CLASSES_KV if kv >= primary_kv), None)


def size_distribution(values: list[float]) -> list[dict] | None:
    """Share of values in each half-open bin [lower, upper); None when there are no values."""
    if not values:
        return None
    counts = [0] * len(SIZE_BIN_EDGES)
    for value in values:
        index = max(i for i, lower in enumerate(SIZE_BIN_EDGES) if value >= lower)
        counts[index] += 1
    bins = []
    for index, share in enumerate(largest_remainder_shares(counts)):
        size_bin = {"gk:lowerBound": SIZE_BIN_EDGES[index], "gk:share": share}
        if index + 1 < len(SIZE_BIN_EDGES):
            size_bin["gk:upperBound"] = SIZE_BIN_EDGES[index + 1]
        bins.append(size_bin)
    return bins


def _nonnegative(path: Path, obj, attribute: str, value: float) -> float:
    if value < 0:
        raise ValueError(f"{path}: {type(obj).__name__} {obj.mRID}: {attribute} is negative")
    return value


def _load_kw(load) -> float | None:
    """The load's real power: its own p, else the sum of its phases' p."""
    if load.p is not None:
        return load.p.to("kW")
    phases = load.EnergyConsumerPhase
    if phases and all(phase.p is not None for phase in phases):
        return sum(phase.p.to("kW") for phase in phases)
    return None


def _round_si(value: float) -> float:
    """Kilo-unit values to three decimals: whole volts, metres and volt-amperes."""
    # contract 4.5a
    return round(value, 3)


def _topology_properties(topology: Topology) -> dict:
    path = topology.path
    record = {"gk:primaryVoltage": _round_si(topology.primary_kv)}
    record["gk:voltageClass"] = voltage_class(topology.primary_kv)
    lengths_km = []
    for segment in topology.feeder_objects(cim.ACLineSegment):
        if _equipment_kv(path, segment) != topology.primary_kv:
            continue
        if segment.length is None:
            raise ValueError(
                f"{path}: ACLineSegment {segment.mRID}: cim:Conductor.length is not set"
            )
        lengths_km.append(
            (segment, _nonnegative(path, segment, "length", segment.length.to("km")))
        )
    record["gk:feederLength"] = _round_si(sum(length for _, length in lengths_km))
    record["gk:undergroundShare"] = _underground_share(lengths_km)
    return record


def _underground(segment) -> bool | None:
    """True for a cable, False for an overhead wire, None when the wire is not known."""
    infos = [segment.AssetDatasheet, *(phase.WireInfo for phase in segment.ACLineSegmentPhases)]
    kinds = set()
    for info in infos:
        if isinstance(info, cim.CableInfo):
            kinds.add(True)
        elif isinstance(info, cim.OverheadWireInfo):
            kinds.add(False)
    return kinds.pop() if len(kinds) == 1 else None


def _underground_share(lengths_km: list) -> float | None:
    """Left out unless every primary segment is known to be overhead or underground."""
    total = sum(length for _, length in lengths_km)
    underground = 0.0
    for segment, length in lengths_km:
        kind = _underground(segment)
        if kind is None:
            return None
        underground += length if kind else 0.0
    if total == 0:
        return None
    return round_share(underground, total)


def _substation_properties(topology: Topology) -> dict:
    high_sides, low_sides = [], []
    path = topology.substation.path
    for transformer in topology.feeding_transformers:
        ends = topology.ends[transformer.identifier]
        high = max(ends, key=lambda end: _end_kv(path, end))
        high_sides.append(topology.connection(high))
        low = [end for end in ends if _end_kv(path, end) == topology.primary_kv]
        low_sides.append(topology.connection(low[0]) if low else None)
    if topology.feeding_transformers:
        return {
            "gk:hvConnection": most_common_connection(high_sides),
            "gk:mvConnection": most_common_connection(low_sides),
        }
    # contract 4.5a: the EnergySource on the feeding bus is WyeGrounded unless grounded is false.
    source_connections = [
        "Wye" if source.grounded is False else "WyeGrounded" for source in topology.feeding_sources
    ]
    return {"gk:mvConnection": most_common_connection(source_connections)}


def _voltage_control_properties(topology: Topology) -> dict:
    """A regulator bank at the feeder head, or an LTC on the feeding transformer or on a
    regulator of its bus, is the substation LTC; every other feeder regulator bank is a line
    regulator."""
    # contract 4.5a: at the head = the bank shares a node with the head device, whose feeder-side
    # node is the head node (3.5).
    line_banks = [bank for bank in topology.regulator_banks if not bank & topology.head_nodes]
    at_head = len(line_banks) < len(topology.regulator_banks)
    station_units = [*topology.feeding_transformers, *topology.bus_regulators]
    substation_ltc = at_head or any(topology.has_ltc(unit) for unit in station_units)
    shunts = topology.feeder_objects(cim.ShuntCompensator)
    capacitor_banks = {topology.terminal_nodes(shunt) for shunt in shunts}
    return {
        "gk:substationLTC": substation_ltc,
        "gk:regulatorCount": len(line_banks),
        "gk:capacitorCount": len(capacitor_banks),
    }


def _load_properties(topology: Topology) -> dict:
    path = topology.path
    loads = topology.feeder_objects(cim.EnergyConsumer)
    customer_counts = [load.customerCount for load in loads]
    kws = [_load_kw(load) for load in loads]
    distribution = None
    if None not in kws:
        sizes = [_nonnegative(path, load, "p", kw) for load, kw in zip(loads, kws, strict=True)]
        distribution = size_distribution(sizes)
    return {
        "gk:loadCount": len(loads),
        "gk:customerCount": None if None in customer_counts else sum(customer_counts),
        "gk:loadSizeDistribution": distribution,
    }


def _der_properties(topology: Topology) -> dict:
    # contract 4.5a: the excluded source is the EnergySource; every SynchronousMachine counts.
    units = [
        *topology.feeder_objects(cim.PowerElectronicsConnection),
        *topology.feeder_objects(cim.SynchronousMachine),
    ]
    record = {"gk:dgCount": len(units)}
    if all(unit.ratedS is not None for unit in units):
        kvas = [
            _nonnegative(topology.path, unit, "ratedS", unit.ratedS.to("kVA")) for unit in units
        ]
        record["gk:dgCapacityAC"] = _round_si(sum(kvas))
        record["gk:dgSizeDistribution"] = size_distribution(kvas)
    return record


def _protection_properties(topology: Topology) -> dict:
    return {
        "gk:fuseCount": len(topology.feeder_objects(cim.Fuse)),
        "gk:recloserCount": len(topology.feeder_objects(cim.Recloser)),
        "gk:sectionalizerCount": len(topology.feeder_objects(cim.Sectionaliser)),
    }


def _component_finder(topology: Topology, equipment_list: list):
    """A function from a connectivity node to its component: nodes joined through each closed
    piece of equipment in the list."""
    parent = {}

    def find(node):
        parent.setdefault(node, node)
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for equipment in equipment_list:
        if isinstance(equipment, cim.Switch) and equipment.normalOpen:
            continue
        nodes = sorted(topology.terminal_nodes(equipment))
        for node in nodes[1:]:
            parent[find(node)] = find(nodes[0])
    return find


def _secondary_properties(topology: Topology) -> dict:
    """gk:secondaryModeling and gk:lowVoltageNetwork from the components below the distribution
    transformers."""
    # contract 4.5a. Loads outside every transformer's secondary are on the primary. With
    # secondary loads, AggregateLoad when each secondary has at most one load, else
    # IndividualCustomers. A secondary fed by two or more transformers is a low-voltage network.
    # A secondary never crosses a transformer.
    component_of = _component_finder(
        topology,
        [
            equipment
            for equipment in topology.feeder_objects(cim.ConductingEquipment)
            if not isinstance(equipment, (cim.PowerTransformer, cim.AutoTransformer))
        ],
    )
    feeding = Counter()
    for transformer in topology.distribution_transformers:
        ends = topology.ends[transformer.identifier]
        top_kv = max(_end_kv(topology.path, end) for end in ends)
        lower_nodes = _nodes(end.Terminal for end in ends if _end_kv(topology.path, end) < top_kv)
        for component in {component_of(node) for node in lower_nodes}:
            feeding[component] += 1
    loads_per_secondary = Counter()
    loads = topology.feeder_objects(cim.EnergyConsumer)
    for load in loads:
        nodes = _nodes(load.Terminals)
        if not nodes:
            raise ValueError(
                f"{topology.path}: EnergyConsumer {load.mRID} has no connected cim:Terminal"
            )
        component = component_of(min(nodes))
        if component in feeding:
            loads_per_secondary[component] += 1
    record = {"gk:lowVoltageNetwork": any(count > 1 for count in feeding.values())}
    if not loads:
        return record
    if not loads_per_secondary:
        record["gk:secondaryModeling"] = "gk:SecondaryModeling.None"
    elif max(loads_per_secondary.values()) == 1:
        record["gk:secondaryModeling"] = "gk:SecondaryModeling.AggregateLoad"
    else:
        record["gk:secondaryModeling"] = "gk:SecondaryModeling.IndividualCustomers"
    return record


def geographic_specificity(topology: Topology) -> str:
    """LatLong when every position of the feeder frame is in a WGS84 CoordinateSystem, XY for any
    other positions, None without positions."""
    points = topology.feeder_objects(cim.PositionPoint)
    if not points:
        return NO_POSITIONS
    for point in points:
        location = point.Location
        crs = location.CoordinateSystem if location is not None else None
        if crs is None or crs.crsUrn is None or crs.crsUrn.strip().lower() not in WGS84_CRS:
            return "gk:GeographicSpecificity.XY"
    return "gk:GeographicSpecificity.LatLong"


def _secondary_connection(topology: Topology, transformer) -> str | None:
    """The connection of end 2; a tank-shaped transformer's tanks must agree."""
    ends = [end for end in topology.ends[transformer.identifier] if end.endNumber == 2]
    connections = {topology.connection(end) for end in ends}
    return connections.pop() if len(connections) == 1 else None


def structural_properties(jsonld_dir: Path, model_id: str) -> dict:
    """Every model-derived property of contract 4.2, keyed by compact IRI; unknown values are
    None. `jsonld_dir` is the package's jsonld/ directory; `model_id` names its feeder frame."""
    topology = Topology(*read_models(Path(jsonld_dir), model_id))
    return {
        **_topology_properties(topology),
        **_substation_properties(topology),
        "gk:lvConnection": most_common_connection(
            [
                _secondary_connection(topology, transformer)
                for transformer in topology.distribution_transformers
            ]
        ),
        **_voltage_control_properties(topology),
        **_load_properties(topology),
        **_der_properties(topology),
        **_protection_properties(topology),
        **_secondary_properties(topology),
        "gk:geographicSpecificity": geographic_specificity(topology),
    }
