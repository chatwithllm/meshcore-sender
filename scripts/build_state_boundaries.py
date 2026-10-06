"""Convert the pinned Census state shapefile to the bundled map GeoJSON.

Requires pyshp==2.3.1. Pass the downloaded cb_2024_us_state_5m.zip as argv[1].
"""

import json
from pathlib import Path
import sys

import shapefile


reader = shapefile.Reader(sys.argv[1], encoding="utf-8")
def rounded(value):
    if isinstance(value, (list, tuple)):
        return [rounded(item) for item in value]
    return round(value, 5)


features = []
for record in reader.iterShapeRecords():
    properties = record.record.as_dict()
    geometry = record.shape.__geo_interface__
    geometry["coordinates"] = rounded(geometry["coordinates"])
    features.append({
        "type": "Feature",
        "properties": {"code": properties["STUSPS"], "name": properties["NAME"]},
        "geometry": geometry,
    })
features.sort(key=lambda feature: feature["properties"]["name"])
output = Path(__file__).resolve().parents[1] / "custom_components/meshcore_sender/www/vendor/us-states.json"
output.write_text(json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")) + "\n", encoding="ascii")
