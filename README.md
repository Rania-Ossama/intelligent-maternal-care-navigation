# Hospital Finder

Drop a pin anywhere in Upper Egypt and the app shows the **nearest hospitals by road**, with road distance,
estimated travel time, phone and address. It compares two shortest-path algorithms (**Enhanced Dijkstra** vs
**Standard Dijkstra**), and, if you add a TomTom key, also shows the **live-traffic time** from TomTom.
Hospitals more than 60 minutes away are flagged in red.

---

## 1. Download the data files

The three data files are too big to include in the project. Download them from Google Drive:

**https://drive.google.com/drive/folders/1Ugnk381b37w10FxLqhEGzfW5w_Z5OqUI?usp=sharing**

You need exactly these three files:

| File | Size | What it is |
|---|---|---|
| `Upper_Egypt_nodes.parquet` | ~86 MB | The **nodes** of the road network: every junction / road point with its id, latitude and longitude. |
| `Upper_Egypt_edges_weighted.parquet` | ~82 MB | The **edges**: the road segments that connect two nodes, with their length and travel time. Together with the nodes this is the road graph. |
| `facilities_flagged.csv` | ~240 KB | The list of **hospitals** (name, location, phone, address, type). |

## 2. Put the files in the `data` folder

Copy all three files into the `data` folder of the project (the folder next to `run.py`):

```
hospital_finder/
├── data/
│   ├── Upper_Egypt_nodes.parquet
│   ├── Upper_Egypt_edges_weighted.parquet
│   └── facilities_flagged.csv
├── run.py
├── start.bat
└── ...
```

Check the file names are exactly as above. If a file has another name, either rename it or change the name in `config.yaml`.

## 3. (Optional) Add your TomTom key

This step is only needed for the live-traffic time and TomTom map. Without a key the app works normally, just without TomTom.

1. In the project folder (next to `run.py`) find the file **`.env.example`**.
2. Make a copy of it and rename the **copy** to exactly **`.env`** (no `.example`, no `.txt`).
   Keep the original `.env.example` as a template.
3. Open `.env` in Notepad and paste your key after the `=`, with no quotes and no spaces:
   ```
   TOMTOM_KEY=your_full_key_here
   ```
4. Save the file.

Get a key at developer.tomtom.com (Dashboard → Keys). Never share your `.env` file or post your key publicly.

## 4. Start the app

**Double-click `start.bat`.** (macOS / Linux: run `./start.sh`.)

You need **Python 3.10 or newer** installed from python.org, with "Add Python to PATH" ticked.
The browser opens at <http://localhost:8000>. Keep the black window open while you use the app; close it to stop the app.

## 5. What happens when you start it

**The very first time (a few minutes):**
1. `start.bat` creates a **`.venv`** folder. This is a private Python environment, so the app's packages don't
   mix with anything else on your computer.
2. It installs the required packages (FastAPI, pandas, etc.) into `.venv`.
3. The app reads the two `.parquet` files and **builds the road graph**: it keeps only valid roads, joins small
   gaps in the data, and keeps the largest connected network so a search can never get trapped.
   You will see a loading screen. The result is saved in `data/processed/`.
4. It reads `facilities_flagged.csv`, removes facilities that shouldn't be recommended (under construction, unreliable
   coordinates, too far from a road, etc.), and matches each hospital to its nearest road node.

**Every later start (a few seconds):** the saved graph in `data/processed/` is loaded directly, so it starts fast.

**When you search:**
1. You drop a pin on the map (inside Egypt). The app snaps it to the nearest road node.
2. **Enhanced Dijkstra** walks the road graph from that node and stops as soon as the nearest hospitals are found.
   **Standard Dijkstra** then explores the whole graph for comparison, and the timing of both is shown.
3. Each hospital card shows road distance, estimated time, phone and address, and the route is drawn on the map.
4. If TomTom is set up, each card also shows **Live traffic (TomTom)** and a dashed black line with TomTom's own route.

## 6. Using the page

- Click the map to drop a pin, or type the latitude / longitude. Drag the pin to move it.
- **Find nearest hospitals** shows the closest 5. **Show 5 more hospitals** adds ranks 6–10.
- Click a hospital card to zoom to its route. Untick the box on a card to hide its route.
- **Show all hospitals considered** shows every hospital the app may recommend (red dots).
- **Live traffic on map** shows TomTom's traffic colours on the map (needs a TomTom key).

## 7. Good to know

- **Estimated time** (Dijkstra) uses assumed speeds per road type, with no traffic. **Live traffic (TomTom)** is the
  current time with traffic. The two can differ, especially across the Nile. If they differ a lot, a bridge may be
  missing or invented in the road data.
- TomTom's traffic data is thinner in Upper Egypt than in big cities, so live and normal times may be similar there.
- Changing the data: replace the files in `data/`. The app notices within seconds and rebuilds the graph by itself.
  To force a rebuild, delete the `data/processed/` folder and start again.
- You can delete the `sample_data/` folder. It is only for a demo without real data.

## 8. Troubleshooting

| Problem | Fix |
|---|---|
| "nodes / edges file was not found" | The files are not in `data/` or are named differently. |
| Setup failed in `start.bat` | Install Python 3.10+ from python.org and tick "Add Python to PATH". |
| "Not enough memory" | Close other programs. Building the graph needs about 2 GB of free memory. |
| Map is grey | No internet for the map tiles. Markers and routes still work. |
| Port already in use | Run `python run.py --port 8010` |
| Card says "Live traffic: not available" | Open `http://localhost:8000/api/tomtom/route?from_lat=26.35&from_lon=31.89&to_lat=26.34&to_lon=31.88` in the browser; the message explains why (missing `.env`, wrong key, or network/antivirus problem). |
| `CERTIFICATE_VERIFY_FAILED` for TomTom | Antivirus / VPN is scanning HTTPS. Run `pip install truststore` (it is already in `requirements.txt`), or turn off HTTPS scanning. |

More technical details (graph building rules, which hospitals are filtered, diagnosing a route) are in `README_DETAILED.md`.
