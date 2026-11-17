# Grid Kitchen feeder VT-0a1b2c3d4e v1.0.0

Rural 12.47 kV distribution feeder in VT with 1,740 loads and 74 DGs; individual customers on transformer secondaries.

- Landing page: https://gridkitchen.pnnl.gov/models/VT-0a1b2c3d4e/1.0.0
- Cite as: Pacific Northwest National Laboratory. Grid Kitchen distribution model VT-0a1b2c3d4e, version 1.0.0 [Data set]. https://gridkitchen.pnnl.gov/models/VT-0a1b2c3d4e/1.0.0. urn:uuid:7cbe316f-83e1-5cb9-a922-d6d98e531a24

## Files

| File | What it is |
|---|---|
| `VT-0a1b2c3d4e.jsonld` | CIM JSON-LD (cim18v17 profile, SI units) |
| `VT-0a1b2c3d4e.xml` | CIM RDF/XML |
| `cimtbl/VT-0a1b2c3d4e.cimtbl` | `.cimtbl` master; it loads the other files in `cimtbl/` |
| `notebook.ipynb` | Opens each format and exports an OpenDSS deck |
| `manifest.jsonld` | Every file with its size and SHA-256, and how this feeder joins other feeders |
| `LICENSE.txt`, `DISCLAIMER.txt` | License and disclaimer |

## Open the model

```bash
pip install "cim-graph==0.6.1" "cim-profiles==0.2.0" "cim-tables==0.2.0a1" "cimhub-opendss==3.0.0" "opendssdirect.py==0.10.0"
```

```python
import os

os.environ["CIMG_CIM_PROFILE"] = "cim18v17"
os.environ["CIMG_USE_UNITS"] = "true"
os.environ["CIMG_ALLOW_REMOTE_CONTEXT"] = "false"

from cimgraph.databases import JSONLDFile
from cimgraph.models import NodeBreakerModel
from cimhub_opendss import cim_to_dss

network = NodeBreakerModel(container=None, connection=JSONLDFile("VT-0a1b2c3d4e.jsonld"), distributed=False)
cim_to_dss(network, "opendss/jsonld/VT-0a1b2c3d4e.dss", switch_state="normal")
```

`notebook.ipynb` does the same for the CIM XML and `.cimtbl` files, and solves the deck with OpenDSS.

## Data sources

| Component | Source | Notes |
|---|---|---|
| Topology | 🟢 From source data | spans and devices from GIS; devices placed by their leaders |
| Conductors | 🟡 Inferred (36% from source) | conductor type from GIS; default 40 ft pole where the pole height is blank |
| Distribution transformers | 🟡 Inferred (52% from source) | kVA from GIS; secondary voltage inferred from kVA and node; %Z: median of valid tanks where GIS has 0 |
| Substation source | 🟡 Inferred (0% from source) | typical source impedance |
| Loads | 🟡 Inferred (0% from source) | locations from GIS meters; kW: each transformer at 30% of nameplate kVA, split over its meters, pf 0.9 |
| DER | 🟢 From source data | ratings from GIS; 2 blank sizes set to the median of their kind |
| Protection | 🟢 From source data | locations from GIS; 13 fuses without a rating |
| Voltage control | 🟡 Inferred (60% from source) | capacitor kVAr from GIS; regulator control settings assumed: 122.5 V +- 2.5 V |
| Secondary | 🔴 Missing | secondary conductors are not in the GIS export |
| Coordinates | 🟢 From source data | node coordinates from GIS |
| Time series | 🔴 Missing | no load or DER profiles in the source |

## License

Released under the BSD 3-Clause license; see `LICENSE.txt` and `DISCLAIMER.txt`.
