# Hospital Finder – nearest hospitals by road (Upper Egypt)

Drop a pin anywhere in Egypt (or type the coordinates) and the app shows the **5 nearest hospitals by road** (and **5 more** with one press of *Show 5 more hospitals*),
each with road distance, estimated travel time, phone and address, and compares the compute time of
**Enhanced Dijkstra** (early exit) with **Standard Dijkstra** (whole graph). Any hospital whose estimated
travel time is **over 60 minutes is flagged in red**.

## 1. Run it

You need **Python 3.10 or newer** (3.11+ recommended). An internet connection is needed only for the map tiles.

1. Put your three files in the `data/` folder (names are set in `config.yaml`):
   * `Upper_Egypt_nodes.parquet`
   * `Upper_Egypt_edges_weighted.parquet`
   * `facilities_flagged.csv`  (or `final_maternal_facilities_clean.csv` – change the name in `config.yaml`)
2. Start it
   * **Windows:** double-click `start.bat`
   * **macOS / Linux:** `./start.sh`
   * or manually: `pip install -r requirements.txt` then `python run.py`
3. The browser opens at <http://localhost:8000>.

**First start:** the app builds the road graph from your parquet files and shows a loading screen
(roughly a minute or a few minutes for the full 2.3M-node network). The result is saved in
`data/processed/`. **Every later start just loads that saved file** (a few seconds).

Memory: building needs about 1.5–2 GB of free RAM, serving about 1 GB.

### Try it without your data
```
python tools/make_sample_data.py
python run.py --config sample_data/config.sample.yaml
```
Then try the pin `27.5590, 31.1590` (two of the three hospitals are flagged as over 1 hour).

## 2. Using the page
* Click the map to drop a pin (only possible **inside Egypt**; outside Egypt is shaded). Drag it to move it.
* The pin fills the **Latitude / Longitude** boxes; you can edit them (the pin follows). Arabic digits,
  decimal commas and pasted `27.18, 31.18` all work.
* **Find nearest hospitals** → 5 cards + coloured routes. **Show 5 more hospitals** (once per search) adds ranks 6–10. Change both numbers in `config.yaml` → `search.results` / `search.more_results`.
* **Show all hospitals considered** (red dots) is ticked by default; untick it to hide them.
* Click a card to zoom to its route; tick/untick to hide a route.
* **Algorithm timing** shows compute time and nodes settled for both algorithms. Enhanced appears immediately;
  Standard runs in the background (seconds) and fills in when finished.

## 3. Updating the data later
| You change… | What happens |
|---|---|
| `facilities_flagged.csv` | Re-read automatically on the next search. No restart. |
| nodes / edges parquet | Detected within ~5 s (size or modified time). The page shows the loading screen, the graph is rebuilt and reloaded automatically. |
| `config.yaml` | Restart the app. Graph-related settings also trigger a rebuild. |
| Force a rebuild | Delete `data/processed/` and restart, or `POST /api/admin/rebuild`. |

If a replacement file is broken, the app keeps showing a clear error (and, for the facilities CSV, keeps serving the
last good list) until you fix it.

## 4. What the graph builder does (embedded in `app/graph_builder.py`)
1. Reads only the needed columns (`id, lon, lat` / `u, v, length, travel_time_s`) – the heavy `geometry` column is skipped.
2. If the edges file has no `travel_time_s`, computes it from `length` + `maxspeed`/`highway` (speed table in `config.yaml`).
3. Removes edges with unknown nodes, self loops, invalid weights, and keeps the fastest of duplicate edges.
4. **Stitches gaps:** every disconnected piece with ≥ 25 nodes lying ≤ 500 m from the main network is joined with a
   two-way bridge edge (30 km/h). Repeated up to 4 rounds. Every bridge is logged in `data/processed/stitched_edges.csv`.
5. Keeps only the **largest strongly connected component**, so a search can never be trapped in an island or a one-way dead end.
6. Writes `graph_nodes.parquet`, `graph_edges.parquet`, `graph_meta.json` (written last, atomically).

Hospitals and the pin are snapped only to this cleaned network.

## 5. Which facilities can be recommended (`config.yaml → facilities`)
* kept: tier `T1_maternity_hospital`, `T2_general_hospital_unverified`, and `T3_unspecified_hospital_unverified` **only if the name contains "مستشف…" / "hospital"**
* removed: `T4_needs_review`, names containing *under construction / قيد الإنشاء*, *post office*, *veterinary*; categories veterinary / restricted-access;
  unreliable coordinates (`coord_reliable = False`); missing or non-Egypt coordinates; hospitals more than 1 km from any road
* facilities on the same road node are **one location** (e.g. CE00001 / CE00009) and shown once with "also registered at this location"
* phones come from the `phone` column (as text, so the leading 0 is kept)

`data/processed/` stats and the number of removed rows per reason are visible at `/api/status`.

## 6. "Why is the nearest hospital so far away?" (missing bridges etc.)
The app measures **road** time, not straight-line distance. A hospital across a river is only close if a bridge connects the roads.
Three things help you check this:
* **Each hospital card shows the straight-line distance** and warns ("Long detour") when the road is 3x longer or more
  (`search.detour_warn_ratio` in `config.yaml`).
* **`data/processed/dropped_pieces.csv`** lists every road piece (5+ nodes) that was cut off and removed, with its location,
  size, gap to the main network and the reason. A cut-off bridge looks like a long thin piece (a few hundred metres to about 2 km).
* **`tools/diagnose_route.py`** explains one route or one hospital:
```
python tools/diagnose_route.py --from 28.0900 30.7500 --to 28.1000 30.7800
python tools/diagnose_route.py --from 28.0900 30.7500 --facility CE00123
```
  It shows the road vs straight-line distance, why a facility was filtered out, saves the route as GeoJSON
  (drag it into geojson.io), and lists dropped pieces near the route.
If a bridge piece was dropped, lower `graph.stitching.min_component_nodes` (e.g. 5) and/or raise `max_gap_m`, delete `data/processed/`, restart.
If the bridge is not in the dropped list either, it is missing earlier (the OSM extraction in the Road Network notebook).

## 7. Notes and limits
* **ETAs are estimates** from assumed speeds per road type (e.g. 30 km/h residential), not traffic.
* Both algorithms must return identical hospitals/times; the app checks this on every search and warns if they ever differ.
* Timing measures the search only (not snapping, JSON or drawing). Searches run one at a time on a single worker
  so timings are clean; a newer search cancels an older Standard run. This is built for a demo or a few users, not heavy traffic.
* The Egypt outline is approximate (a few km at the coast; slightly generous over the sea).
* Pins in Egypt but outside the road data (e.g. Cairo) are refused with a message, because the road data covers Upper Egypt only.
* Not covered: building the parquet files from the raw OSM `.pbf` (that remains in the Road Network notebook).

## 8. Troubleshooting
| Message | Fix |
|---|---|
| "nodes/edges file was not found" | Put the file in `data/` or fix the path in `config.yaml`. |
| "missing column 'x'" | Fix `columns:` in `config.yaml` (the message lists the columns found). |
| "Not enough memory" | Close other programs; the full graph needs ~2 GB free while building. |
| Map is grey | No internet for the tiles; routes and markers still work. |
| "No facilities remain after applying the filters" | Check `facilities.include_tiers` in `config.yaml`. |
| Port in use | `python run.py --port 8010` |

## 9. Project layout
```
config.yaml            all paths, column names, filters, thresholds
run.py / start.bat / start.sh
app/   main.py (API)  manager.py (build/load/watch)  graph_builder.py  graph_store.py
       algorithms.py (both Dijkstras)  facilities.py  search_service.py  egypt.py  config.py
frontend/  index.html  app.js  style.css  vendor/leaflet (bundled, no CDN)
data/      your input files; data/processed/ is created by the app
tools/make_sample_data.py  tools/diagnose_route.py   tests/ (pytest)   sample_data/
```
API: `GET /api/status`, `GET /api/config`, `GET /api/facilities`, `POST /api/search {lat, lon}`,
`GET /api/baseline/{job_id}`, `POST /api/admin/rebuild`. Tests: `pip install -r requirements-dev.txt && pytest -q`.
