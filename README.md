# Oil Spill Segmentation Viewer
**Interactive Leaflet map viewer — Glodal Inc., Japan**

---

## Quickest way to run (Windows)

1. Extract the zip
2. Double-click **`START_VIEWER.bat`**
3. Browser opens automatically at http://localhost:8050

That's it. Credentials are already set in the `.bat` file.

---

## Directory layout

```
oilspill_viewer/
├── START_VIEWER.bat          ← Double-click to launch (Windows)
├── backend/
│   ├── app.py                ← FastAPI server
│   ├── requirements.txt
│   └── cache/                ← auto-created on first run
└── frontend/
    └── index.html            ← Leaflet viewer
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "Backend unreachable" / OFFLINE | Make sure `START_VIEWER.bat` window is still open (server stops when you close it) |
| Server window closes immediately | Run `python app.py` directly from CMD to see the error message |
| Scene list empty (0 scenes) | Check VPN — your laptop needs to reach `rgw.glodal-inc.net` |
| First scene click is slow (10–30s) | Normal — backend downloads + renders PNG from S3. Cached instantly after. |
| Port 8050 already in use | Edit `START_VIEWER.bat`, change `set PORT=8050` to `set PORT=8051` |

---

## Adding new scenes

Upload `*_clean.tif` files to `Oil_Spill_Postprocessed_v15/` in S3.  
The viewer discovers them automatically — click ↻ in the sidebar or wait 2 minutes.

---

## Changing S3 paths or credentials

Edit `START_VIEWER.bat` — all settings are at the top of the file.

---

## Running on JupyterHub / Linux

```bash
cd backend
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret
python app.py
```
