#!/usr/bin/env python3
"""
precache_for_viewer.py
======================
Run this on JupyterHub to pre-generate all SAR + mask PNGs and upload
them to S3. After this, the web viewer loads instantly with no rendering
delay — it just fetches the cached PNGs directly.

Usage (on JupyterHub):
    pip install rasterio boto3 Pillow numpy --quiet
    python precache_for_viewer.py

What it does:
    1. Lists all *_clean.tif from Oil_Spill_Postprocessed_v15/
    2. Matches each to its SAR TIF in Preprocess_After_SNAP_/
    3. Downloads each TIF, reprojects to WGS84, renders PNG
    4. Uploads PNGs + metadata JSON to:
         s3://Inference_Oil_Spill_segmentation/
              oil_spill_brazil/Output/Viewer_Cache/{scene_id}/sar.png
              oil_spill_brazil/Output/Viewer_Cache/{scene_id}/mask.png
              oil_spill_brazil/Output/Viewer_Cache/{scene_id}/meta.json
    5. The web viewer's backend reads from this cache prefix automatically.

Resume-friendly: skips scenes where meta.json already exists in S3.

QGIS-matching rendering:
    SAR : Singleband gray, Black→White, STRETCH TO MIN/MAX of valid pixels
          (matches QGIS "Min / max" with Cumulative count cut 2.0-98.0%
           using the Min/max radio button override — actual QGIS min/max)
    Mask: Binary threshold >= 128 → amber (245,166,35) RGBA overlay
          Transparent outside oil pixels

PROJ note: On JupyterHub PROJ works correctly so WarpedVRT reprojection
           produces geometrically perfect results. This is why we pre-cache
           here rather than rendering on Windows where PostgreSQL breaks PROJ.
"""

import json
import logging
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import boto3
import numpy as np
from PIL import Image

# ── rasterio ─────────────────────────────────────────────────────────────────
import rasterio
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from rasterio.warp import transform_bounds

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("precache")

# =============================================================================
# ── CONFIGURATION — edit if needed ───────────────────────────────────────────
# =============================================================================

S3_ENDPOINT  = "https://rgw.glodal-inc.net"
S3_BUCKET    = "Inference_Oil_Spill_segmentation"
S3_MASK_ROOT = "oil_spill_brazil/Output/Oil_Spill_Postprocessed_v15"
S3_SAR_ROOT  = "oil_spill_brazil/Output/Preprocess_After_SNAP_"
S3_CACHE_ROOT= "oil_spill_brazil/Output/Viewer_Cache_Final"   # where PNGs are uploaded

# Credentials — set as env vars before running:
#   export AWS_ACCESS_KEY_ID=...
#   export AWS_SECRET_ACCESS_KEY=...
# OR set them directly here (not recommended for shared systems):
AWS_ACCESS_KEY_ID     = os.environ.get("AWS_ACCESS_KEY_ID",     "PB1VCH7O58UFUM53PTBT")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY", "vK3ZpOC94kcCj94TWTnwg5FvMk288BLCCKlvCfnj")

# Render settings
MAX_SAR_DIM      = 3000    # SAR PNG max dimension (pixels). 3000 = good quality
MAX_MASK_DIM     = 5000    # Mask is small (~7MB), keep higher resolution
MASK_THRESHOLD   = 128     # pixels >= this = oil
MASK_COLOR_RGBA  = (245, 166, 35, 235)  # amber, matches viewer legend
SAR_STRETCH_MODE = "minmax"  # "minmax" matches QGIS Min/Max exactly
                              # "percentile" uses 2-98% clip if preferred

# Ceph RGW fix — disable checksum mismatch
os.environ["AWS_REQUEST_CHECKSUM_CALCULATION"] = "when_required"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

# =============================================================================
# HELPERS
# =============================================================================

DATE_KEY_RE = re.compile(
    r"(\d{8}T\d{6}_\d{8}T\d{6}_[0-9A-Fa-f]{6}_[0-9A-Fa-f]{6}_[0-9A-Fa-f]{4})"
)

def date_key(name: str):
    m = DATE_KEY_RE.search(name)
    return m.group(1) if m else None

def scene_id_from_mask_key(key: str) -> str:
    base = os.path.basename(key)
    return base[:-len("_clean.tif")] if base.endswith("_clean.tif") else Path(base).stem

def parse_dt(dk: str):
    try:
        return datetime.strptime(dk.split("_")[0], "%Y%m%dT%H%M%S")
    except Exception:
        return None

def _s3():
    return boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name="us-east-1",
    )

def s3_exists(s3, key: str) -> bool:
    try:
        s3.head_object(Bucket=S3_BUCKET, Key=key)
        return True
    except Exception:
        return False

def s3_upload(s3, data: bytes, key: str, content_type: str = "application/octet-stream"):
    s3.put_object(Bucket=S3_BUCKET, Key=key, Body=data, ContentType=content_type)

def s3_download_tmp(s3, key: str, suffix=".tif") -> str:
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp.close()
    log.info("    ↓ downloading %s ...", os.path.basename(key))
    s3.download_file(S3_BUCKET, key, tmp.name)
    return tmp.name

# =============================================================================
# RASTER RENDERING
# =============================================================================

WKT_4326 = (
    'GEOGCS["WGS 84",DATUM["WGS_1984",'
    'SPHEROID["WGS 84",6378137,298.257223563]],'
    'PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]]'
)

def crs_4326():
    return rasterio.crs.CRS.from_wkt(WKT_4326)


def read_tif_wgs84(local_path: str, max_dim: int) -> tuple:
    """
    Read TIF, reproject to WGS84, decimate to max_dim.
    Returns (array float32, bounds [south, west, north, east]).
    """
    dst_crs = crs_4326()

    with rasterio.open(local_path) as src:
        nodata = src.nodata
        with WarpedVRT(src, crs=dst_crs,
                       resampling=Resampling.bilinear,
                       src_nodata=nodata, nodata=nodata) as vrt:

            scale = min(1.0, max_dim / max(vrt.width, vrt.height))
            out_h = max(1, int(round(vrt.height * scale)))
            out_w = max(1, int(round(vrt.width  * scale)))

            data = vrt.read(1,
                            out_shape=(out_h, out_w),
                            resampling=Resampling.bilinear
                           ).astype(np.float32)

            tf    = vrt.transform
            west  = tf.c
            north = tf.f
            px_w  = tf.a * (vrt.width  / out_w)
            px_h  = tf.e * (vrt.height / out_h)
            east  = west  + out_w * px_w
            south = north + out_h * px_h

    if nodata is not None:
        data = np.where(data == nodata, np.nan, data)

    bounds = [float(south), float(west), float(north), float(east)]
    return data, bounds


def render_sar(local_path: str) -> tuple:
    """
    SAR → grayscale RGBA PNG with QGIS-matching Min/Max stretch.
    Returns (png_bytes, bounds).
    """
    log.info("    Rendering SAR (QGIS Min/Max stretch, max_dim=%d)...", MAX_SAR_DIM)
    data, bounds = read_tif_wgs84(local_path, MAX_SAR_DIM)
    h, w = data.shape

    valid = data[np.isfinite(data)]
    if SAR_STRETCH_MODE == "minmax":
        lo, hi = float(valid.min()), float(valid.max())
    else:
        lo, hi = float(np.percentile(valid, 2)), float(np.percentile(valid, 98))
    if hi <= lo:
        hi = lo + 1e-6
    log.info("      SAR value range: %.3f → %.3f  (stretch %.3f → %.3f)",
             float(valid.min()), float(valid.max()), lo, hi)

    norm = np.clip((data - lo) / (hi - lo), 0.0, 1.0)
    gray = (norm * 255).astype(np.uint8)
    mask_alpha = np.where(np.isfinite(data), 255, 0).astype(np.uint8)

    # RGBA — gray with alpha (transparent where nodata)
    rgba = np.stack([gray, gray, gray, mask_alpha], axis=-1)
    buf = BytesIO()
    Image.fromarray(rgba, "RGBA").save(buf, format="PNG")
    log.info("      SAR PNG: %dx%d, %.1f KB", w, h, len(buf.getvalue())/1024)
    return buf.getvalue(), bounds


def render_mask(local_path: str) -> tuple:
    """
    Mask → amber RGBA PNG. Pixels >= MASK_THRESHOLD = amber, else transparent.
    Returns (png_bytes, bounds, stats_dict).
    """
    log.info("    Rendering oil mask (max_dim=%d, threshold=%d)...", MAX_MASK_DIM, MASK_THRESHOLD)
    data, bounds = read_tif_wgs84(local_path, MAX_MASK_DIM)
    h, w = data.shape

    oil      = (np.nan_to_num(data, nan=0) >= MASK_THRESHOLD)
    oil_px   = int(oil.sum())
    # valid = pixels inside the actual SAR swath (finite, non-nodata)
    valid_px = int(np.isfinite(data).sum())
    total_px = int(data.size)
    log.info("      Oil pixels: %d | valid (in-swath): %d | total: %d",
             oil_px, valid_px, total_px)

    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    rgba[oil, 0] = MASK_COLOR_RGBA[0]
    rgba[oil, 1] = MASK_COLOR_RGBA[1]
    rgba[oil, 2] = MASK_COLOR_RGBA[2]
    rgba[oil, 3] = MASK_COLOR_RGBA[3]
    # outside-swath pixels stay alpha=0 (transparent)

    buf = BytesIO()
    Image.fromarray(rgba, "RGBA").save(buf, format="PNG")
    log.info("      Mask PNG: %dx%d, %.1f KB", w, h, len(buf.getvalue())/1024)

    # ── Correct area from ORIGINAL TIF (before reprojection) ──────────────────
    # The reprojected array has degrees as pixel units → wrong area if used directly.
    # Open the original local TIF for its native transform + CRS.
    area_km2   = 0.0
    pixel_size = None
    try:
        with rasterio.open(local_path) as src:
            tr  = src.transform
            crs = src.crs
            pw  = abs(float(tr.a))
            ph  = abs(float(tr.e))
            log.info("      Native CRS: %s | pixel: %.4f × %.4f %s",
                     crs.to_string() if crs else "None", pw, ph,
                     "m" if (crs and crs.is_projected) else "deg")
            if crs and crs.is_projected:
                # UTM / projected — pixels are in metres, direct calculation
                area_km2   = oil_px * pw * ph / 1e6
                pixel_size = round(pw, 2)
            else:
                # Geographic (degrees) — convert with mid-latitude scale factor
                b    = rasterio.transform.array_bounds(src.height, src.width, tr)
                mlat = (b[1] + b[3]) / 2.0
                mx   = 111_320.0 * np.cos(np.radians(mlat))
                my   = 111_320.0
                area_km2   = oil_px * (pw * mx) * (ph * my) / 1e6
                pixel_size = None  # not a fixed size in metres
    except Exception as e:
        log.warning("      Area calc failed: %s", e)

    # Coverage denominator = valid (in-swath) pixels only
    cov_pct = round(100.0 * oil_px / valid_px, 4) if valid_px > 0 else 0.0
    log.info("      Area: %.3f km²  |  Coverage: %.4f%%  |  pixel=%.1f m",
             area_km2, cov_pct, pixel_size or 0)

    stats = {
        "oil_pixels":   oil_px,
        "valid_pixels": valid_px,
        "total_pixels": total_px,
        "oil_area_km2": round(float(area_km2), 3),
        "coverage_pct": cov_pct,
        "pixel_size_m": pixel_size,
    }
    return buf.getvalue(), bounds, stats


# =============================================================================
# SCENE LISTING
# =============================================================================

def list_all_scenes(s3):
    log.info("Listing mask TIFs from S3...")
    pag = s3.get_paginator("list_objects_v2")

    mask_keys = []
    for pg in pag.paginate(Bucket=S3_BUCKET, Prefix=S3_MASK_ROOT):
        for obj in pg.get("Contents", []):
            k = obj["Key"]
            if k.lower().endswith("_clean.tif"):
                mask_keys.append(k)

    log.info("Listing SAR TIFs from S3...")
    sar_index = {}
    for pg in pag.paginate(Bucket=S3_BUCKET, Prefix=S3_SAR_ROOT):
        for obj in pg.get("Contents", []):
            k = obj["Key"]
            if k.lower().endswith(".tif"):
                dk = date_key(os.path.basename(k))
                if dk:
                    sar_index[dk] = k

    scenes = []
    for mk in sorted(mask_keys):
        sid   = scene_id_from_mask_key(mk)
        dk    = date_key(os.path.basename(mk))
        sar_k = sar_index.get(dk) if dk else None
        dt    = parse_dt(dk) if dk else None
        scenes.append({
            "scene_id": sid,
            "date_key": dk,
            "date":     dt.strftime("%Y-%m-%d") if dt else None,
            "time":     dt.strftime("%H:%M:%S") if dt else None,
            "mask_key": mk,
            "sar_key":  sar_k,
            "has_sar":  sar_k is not None,
        })

    scenes.sort(key=lambda s: s["date_key"] or "", reverse=True)
    log.info("Found %d scenes, %d with SAR", len(scenes), sum(s["has_sar"] for s in scenes))
    return scenes


# =============================================================================
# MAIN
# =============================================================================

def main():
    log.info("=" * 70)
    log.info("OIL SPILL VIEWER — PRE-CACHE GENERATOR")
    log.info("Bucket  : %s", S3_BUCKET)
    log.info("Endpoint: %s", S3_ENDPOINT)
    log.info("Cache   : %s/%s/", S3_BUCKET, S3_CACHE_ROOT)
    log.info("SAR dim : %d px  |  Mask dim: %d px", MAX_SAR_DIM, MAX_MASK_DIM)
    log.info("Stretch : %s", SAR_STRETCH_MODE)
    log.info("=" * 70)

    s3     = _s3()
    scenes = list_all_scenes(s3)

    if not scenes:
        log.error("No scenes found — check S3 paths")
        sys.exit(1)

    completed = skipped = failed = 0

    for idx, scene in enumerate(scenes, 1):
        sid = scene["scene_id"]
        log.info("")
        log.info("─" * 70)
        log.info("[%d/%d]  %s", idx, len(scenes), sid)
        log.info("─" * 70)

        meta_key = f"{S3_CACHE_ROOT}/{sid}/meta.json"
        sar_key  = f"{S3_CACHE_ROOT}/{sid}/sar.png"
        mask_key_out = f"{S3_CACHE_ROOT}/{sid}/mask.png"

        # Resume — skip if already done
        if s3_exists(s3, meta_key):
            log.info("  ⏭  Already cached — skipping")
            skipped += 1
            continue

        t0 = time.time()
        sar_local = mask_local = None

        try:
            # ── Download mask (small, ~7MB) ───────────────────────────
            mask_local = s3_download_tmp(s3, scene["mask_key"])
            mask_png, mask_bounds, stats = render_mask(mask_local)

            # ── Download + render SAR ─────────────────────────────────
            sar_bounds = mask_bounds  # fallback
            sar_png    = None
            if scene["has_sar"]:
                sar_local = s3_download_tmp(s3, scene["sar_key"])
                sar_png, sar_bounds = render_sar(sar_local)

            # ── Build metadata ────────────────────────────────────────
            s, w, n, e = sar_bounds
            meta = {
                "scene_id":    sid,
                "date":        scene["date"],
                "time":        scene["time"],
                "has_sar":     scene["has_sar"],
                "bounds":      [s, w, n, e],
                "center":      [(s+n)/2, (w+e)/2],
                **stats,
                "sar_png_url":  f"/api/cache/{sid}/sar.png"  if scene["has_sar"] else None,
                "mask_png_url": f"/api/cache/{sid}/mask.png",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "generated_on": "jupyterhub",
            }

            # ── Upload to S3 ──────────────────────────────────────────
            log.info("    ↑ uploading mask PNG ...")
            s3_upload(s3, mask_png, mask_key_out, "image/png")

            if sar_png:
                log.info("    ↑ uploading SAR PNG ...")
                s3_upload(s3, sar_png, sar_key, "image/png")

            log.info("    ↑ uploading meta.json ...")
            s3_upload(s3, json.dumps(meta).encode(), meta_key, "application/json")

            elapsed = time.time() - t0
            log.info("  ✅ Done in %.1fs  (oil %.3f km², %.3f%%)",
                     elapsed, stats["oil_area_km2"], stats["coverage_pct"])
            completed += 1

        except Exception as e:
            log.exception("  ❌ FAILED: %s", e)
            failed += 1
        finally:
            for p in [sar_local, mask_local]:
                if p:
                    try: os.unlink(p)
                    except: pass

    log.info("")
    log.info("=" * 70)
    log.info("PRE-CACHE COMPLETE")
    log.info("  ✅ Completed : %d", completed)
    log.info("  ⏭  Skipped   : %d  (already cached)", skipped)
    log.info("  ❌ Failed    : %d", failed)
    log.info("")
    log.info("Now update START_VIEWER.bat with:")
    log.info("  set USE_S3_CACHE=true")
    log.info("  set S3_CACHE_ROOT=%s", S3_CACHE_ROOT)
    log.info("=" * 70)


if __name__ == "__main__":
    main()