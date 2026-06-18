# Running Oil Spill Viewer on JupyterHub

## Step 1 — Upload the zip

Upload `oilspill_viewer_v2.zip` to your JupyterHub home directory, then extract:

```bash
cd ~
unzip oilspill_viewer_v2.zip
cd oilspill_viewer/oilspill_viewer
```

---

## Step 2 — Pre-generate all PNGs (run once, ~1-2 hours for 21 scenes)

This runs on JupyterHub where PROJ works correctly, generating perfect georeferenced PNGs:

```bash
pip install rasterio boto3 Pillow numpy --quiet
python3 precache_for_viewer.py
```

Resume-safe — re-run any time to pick up new scenes. Already-done scenes are skipped.

---

## Step 3 — Start the web server

```bash
chmod +x start_viewer.sh
./start_viewer.sh
```

Or manually:

```bash
export AWS_ACCESS_KEY_ID="*************"
export AWS_SECRET_ACCESS_KEY="*****************"
export AWS_DEFAULT_REGION="us-east-1"
export AWS_REQUEST_CHECKSUM_CALCULATION="when_required"
export S3_ENDPOINT="https://rgw.glodal-inc.net"
export S3_BUCKET="Inference_Oil_Spill_segmentation"
export USE_S3_CACHE="true"
export S3_CACHE_ROOT="oil_spill_brazil/Output/Viewer_Cache"
export PORT=8050
cd backend
python3 app.py
```

---

## Step 4 — Open in browser

After the server starts, open the viewer using the **JupyterHub proxy URL**:

```
https://<your-jhub-domain>/user/<your-username>/proxy/8050/
```

Example:
```
https://jupyter.glodal-inc.net/user/sachin11-2dgeomatics/proxy/8050/
```

The URL format is always: `<JupyterHub base URL>/user/<username>/proxy/8050/`

You can find your username in the JupyterHub terminal with: `echo $JUPYTERHUB_USER`

---

## Run server in background (so it keeps running after closing terminal)

```bash
cd ~/oilspill_viewer/oilspill_viewer
nohup ./start_viewer.sh > viewer.log 2>&1 &
echo "Server started, PID: $!"
echo "Logs: tail -f ~/oilspill_viewer/oilspill_viewer/viewer.log"
```

To stop it later:
```bash
pkill -f "python3 app.py"
```

---

## Quick start (single command copy-paste)

```bash
cd ~/oilspill_viewer/oilspill_viewer && \
  pip install fastapi "uvicorn[standard]" boto3 rasterio Pillow numpy -q && \
  AWS_ACCESS_KEY_ID=************** \
  AWS_SECRET_ACCESS_KEY=******************* \
  AWS_REQUEST_CHECKSUM_CALCULATION=when_required \
  S3_ENDPOINT=https://rgw.glodal-inc.net \
  S3_BUCKET=Inference_Oil_Spill_segmentation \
  USE_S3_CACHE=true \
  S3_CACHE_ROOT=oil_spill_brazil/Output/Viewer_Cache \
  PORT=8050 \
  python3 backend/app.py
```

Then open: `https://<jhub>/user/<username>/proxy/8050/`

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "Address already in use" | `pkill -f "python3 app.py"` then retry, or use `PORT=8051` |
| Scene list shows but map blank | Run `precache_for_viewer.py` first |
| 404 on `/api/...` | Make sure URL ends with `/proxy/8050/` not just `/proxy/8050` |
| Page not found at proxy URL | JupyterHub must have ServerProxy installed: `pip install jupyter-server-proxy` |
