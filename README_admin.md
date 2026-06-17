# Oil Spill Segmentation Viewer — Administrator Guide

*Sentinel-1 SAR · UNet Model · S3-backed Inference Pipeline*

> **Note:** This guide assumes administrator-level access to the GLODAL S3 storage (`rgw.glodal-inc.net`), Apache Airflow, and a JupyterHub-backed Linux environment. Steps must be completed in order, as each stage depends on the output of the previous one.

## Overview

This document describes the end-to-end administrator workflow for processing Sentinel-1 SAR scenes through the oil spill segmentation pipeline and publishing the results to the interactive web viewer. The pipeline has four stages: data upload, model inference, post-processing and caching, and web server deployment.

---

## 1. Upload SAR Data to S3

Upload all raw Sentinel-1 SAR scenes (`S1A_IW_GRDH` format) to the designated input bucket path:

```
https://rgw.glodal-inc.net/Inference_Oil_Spill_segmentation/
  oil_spill_brazil/Input/
    S1A_IW_GRDH_1SDV_20190925T083100_20190925T083129_029175_035013_AB7C/
```

Each scene should be uploaded as its own folder, named after the full Sentinel-1 product identifier, under the `Input/` path shown above.

> **Permission required:** Before uploading, request access from Dr. Miyazaki for control of the `Inference_Oil_Spill_segmentation` S3 bucket. Bucket-level permissions are managed by Dr. Miyazaki and must be granted before any upload or pipeline run can proceed.

---

## 2. Run the Inference and Post-Processing DAGs

Pipeline orchestration is handled through Apache Airflow. Once the SAR scenes are confirmed in the `Input/` bucket, run the following two DAGs in order:

1. **`oilspill_inference`** — runs the UNet segmentation model against the uploaded SAR scenes.
   [airflow.glodal-inc.net/dags/oilspill_inference](https://airflow.glodal-inc.net/dags/oilspill_inference)
2. **`oilspill_postprocess_and_map`** — applies morphological post-processing and prepares the output for mapping.
   [airflow.glodal-inc.net/dags/oilspill_postprocess_and_map](https://airflow.glodal-inc.net/dags/oilspill_postprocess_and_map)

> **Note:** The second DAG depends on the successful completion of the first. Do not trigger `oilspill_postprocess_and_map` until `oilspill_inference` has finished running for all target scenes.

---

## 3. Generate the Viewer Cache

After both DAGs complete, generate the lightweight preview cache used by the web viewer:

```bash
python3 precache_for_viewer.py
```

This script converts the raw GeoTIFF inference outputs into 0–255 grayscale RGBA PNG images. This conversion step exists because rendering full GeoTIFFs directly in the browser is slow and can cause loading failures or timeouts in the viewer.

After the script finishes, verify the cached PNGs were written successfully by checking the output path in S3:

```
https://rgw.glodal-inc.net/Inference_Oil_Spill_segmentation/
  oil_spill_brazil/Output/Viewer_Cache_Final/
```

> **Checkpoint:** If this folder is empty or missing recently dated files, do not proceed to starting the web viewer — re-run `precache_for_viewer.py` and confirm there were no errors in the console output.

---

## 4. Start the Viewer Backend

### Option A — Using the start script

```bash
chmod +x start_viewer.sh
./start_viewer.sh
```

### Option B — Manual environment setup

If the start script is unavailable, export the required environment variables manually and launch the backend directly:

```bash
export AWS_ACCESS_KEY_ID="PB1VCH7O58UFUM53PTBT"
export AWS_SECRET_ACCESS_KEY="vK3ZpOC94kcCj94TWTnwg5FvMk288BLCCKlvCfnj"
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

> **Security:** These credentials grant direct access to the S3 bucket. Treat them as sensitive: do not commit them to version control, share them outside the admin team, or paste them into chat tools. Rotate the access key periodically and request new credentials from Dr. Miyazaki if they may have been exposed.

### Accessing the Viewer via JupyterHub

Once the server is running, it is reachable only through the JupyterHub proxy — not as a standalone public URL. Open the viewer at:

```
https://<your-jhub-domain>/user/<your-username>/proxy/8050/
```

Example:

```
https://jupyter.glodal-inc.net/user/sachin11-2dgeomatics/proxy/8050/
```

The URL always follows the pattern `<JupyterHub base URL>/user/<username>/proxy/8050/`. Find your own JupyterHub username by running the following inside a JupyterHub terminal:

```bash
echo $JUPYTERHUB_USER
```

### Running the Server in the Background

To keep the viewer running after closing the terminal session, launch it with `nohup`:

```bash
cd ~/oilspill_viewer/oilspill_viewer
nohup ./start_viewer.sh > viewer.log 2>&1 &
echo "Server started, PID: $!"
echo "Logs: tail -f ~/oilspill_viewer/oilspill_viewer/viewer.log"
```

To stop the background server:

```bash
pkill -f "python3 app.py"
```

### Quick Start — Single Command

For a one-shot setup that installs dependencies and launches the backend in a single step:

```bash
cd ~/oilspill_viewer/oilspill_viewer && \
  pip install fastapi "uvicorn[standard]" boto3 rasterio Pillow numpy -q && \
  AWS_ACCESS_KEY_ID=PB1VCH7O58UFUM53PTBT \
  AWS_SECRET_ACCESS_KEY=vK3ZpOC94kcCj94TWTnwg5FvMk288BLCCKlvCfnj \
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

## Pipeline Summary

| Step | Action | Where |
|------|--------|-------|
| 1 | Upload SAR scenes (S1A_IW_GRDH) | S3 `Input/` bucket path |
| 2 | Run `oilspill_inference`, then `oilspill_postprocess_and_map` | Apache Airflow |
| 3 | Run `precache_for_viewer.py`; verify PNGs in `Viewer_Cache_Final/` | Terminal + S3 `Output/` bucket |
| 4 | Start backend (`start_viewer.sh` or manual env vars) | JupyterHub terminal |
| 5 | Open viewer via JupyterHub proxy URL | Browser |

---

## Troubleshooting

- **Viewer shows 0 scenes:** confirm `precache_for_viewer.py` completed without errors and that `Viewer_Cache_Final/` in S3 contains recent PNG files.
- **Proxy URL returns 404:** verify `PORT=8050` matches the port used in the proxy path, and that the backend process is still running (check `viewer.log`).
- **Permission denied on S3 upload:** confirm bucket access has been granted by Dr. Miyazaki and that `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` are exported correctly in the current shell session.
- **Server stops after closing terminal:** relaunch using the `nohup` background method described in Section 4 instead of running `app.py` directly in an interactive shell.

---

*GLODAL INC., Japan*
