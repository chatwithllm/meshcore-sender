# State Filter Assets

`us-states.json` is generated from the U.S. Census Bureau's public-domain 2024
1:5,000,000 state and equivalent-entity cartographic boundary shapefile:
https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_state_5m.zip

Source ZIP SHA-256:
`c9db0e395c11a1f94a8017fde4f4c7cbee1dca6eb37ba8f1ccaab927df70885f`.

Generate with `scripts/build_state_boundaries.py` and pyshp 2.3.1. It retains
state names/codes and Polygon/MultiPolygon topology, rounding to five decimal
places. These are generalized cartographic boundaries, not survey-grade borders;
coastal and border-adjacent coordinates can remain unclassified or approximate.
No coordinate is sent to an external geocoder.

`point-in-polygon.js` is a locally bundled Turf booleanPointInPolygon 7.2.0:
https://turfjs.org/docs/7.2.0/api/booleanPointInPolygon

Build input: `scripts/state_geometry_entry.js`. Bundle with esbuild 0.25.0,
`--bundle --minify --format=iife --global-name=MeshCoreGeo`. Resolved runtime
dependencies: @turf/helpers 7.4.0, @turf/invariant 7.4.0,
point-in-polygon-hao 1.2.4 and robust-predicates 3.0.3. MIT and Unlicense notices
are bundled alongside this file. Build dependencies are not required on HA.
