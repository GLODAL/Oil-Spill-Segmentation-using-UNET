#!/bin/bash
# =============================================================================
# start_viewer.sh
# Oil Spill Segmentation Viewer — JupyterHub / Linux startup script
#
# Usage:
#   chmod +x start_viewer.sh
#   ./start_viewer.sh
#
# Then open the URL printed below in your browser.
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
PORT=${PORT:-8050}

echo "============================================"
echo "  Oil Spill Segmentation - UNet Model"
echo "  Glodal Inc., Japan"
echo "============================================"
echo ""

# ── Credentials ──────────────────────────────────────────────────────────────
export AWS_ACCESS_KEY_ID="PB1VCH7O58UFUM53PTBT"
export AWS_SECRET_ACCESS_KEY="vK3ZpOC94kcCj94TWTnwg5FvMk288BLCCKlvCfnj"
export AWS_DEFAULT_REGION="us-east-1"
export AWS_REQUEST_CHECKSUM_CALCULATION="when_required"

# ── S3 config ─────────────────────────────────────────────────────────────────
export S3_ENDPOINT="https://rgw.glodal-inc.net"
export S3_BUCKET="Inference_Oil_Spill_segmentation"
export S3_MASK_ROOT="oil_spill_brazil/Output/Oil_Spill_Postprocessed_v15"
export S3_SAR_ROOT="oil_spill_brazil/Output/Preprocess_After_SNAP_"
export S3_CACHE_ROOT="oil_spill_brazil/Output/Viewer_Cache"
export USE_S3_CACHE="true"
export PORT="$PORT"
export MAX_SAR_DIM="3000"

# ── Install dependencies if needed ───────────────────────────────────────────
echo "Checking dependencies..."
python3 -c "import fastapi, uvicorn, boto3, rasterio, PIL" 2>/dev/null || {
    echo "Installing dependencies..."
    pip install fastapi "uvicorn[standard]" boto3 rasterio Pillow numpy --quiet
}
echo "[OK] Dependencies ready."
echo ""

# ── Detect JupyterHub proxy URL ───────────────────────────────────────────────
echo "──────────────────────────────────────────"
if [ -n "$JUPYTERHUB_SERVICE_PREFIX" ]; then
    # Standard JupyterHub: routes /user/<name>/proxy/<port>/ to the service
    BASE="${JUPYTERHUB_SERVICE_PREFIX%/}"
    echo "  Open in browser:"
    echo "  https://$(hostname)${BASE}/proxy/${PORT}/"
    echo ""
    echo "  Or via JupyterHub dashboard:"
    echo "  <your-jhub-url>/user/$(whoami)/proxy/${PORT}/"
elif [ -n "$JUPYTER_SERVER_URL" ]; then
    echo "  Open in browser:"
    echo "  ${JUPYTER_SERVER_URL%/}/proxy/${PORT}/"
else
    echo "  Open in browser:"
    echo "  http://localhost:${PORT}/"
    echo ""
    echo "  If running on a remote server, use SSH port forwarding:"
    echo "  ssh -L ${PORT}:localhost:${PORT} your-server"
    echo "  then open: http://localhost:${PORT}/"
fi
echo "──────────────────────────────────────────"
echo ""
echo "  Press Ctrl+C to stop the server."
echo ""

# ── Start ─────────────────────────────────────────────────────────────────────
cd "$BACKEND_DIR"
exec python3 app.py
