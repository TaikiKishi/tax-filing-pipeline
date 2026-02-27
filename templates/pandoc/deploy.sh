#!/usr/bin/env bash
# deploy.sh - Deploy invoice Pandoc template to ~/.pandoc/
# Usage: bash templates/pandoc/deploy.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Target directories
PANDOC_DEFAULTS="$HOME/.pandoc/defaults"
PANDOC_TEMPLATES="$HOME/.pandoc/templates/invoice"

echo "=== Invoice Pandoc Template Deploy ==="
echo ""

# Create directories
echo "[1/2] Creating directories..."
mkdir -p "$PANDOC_DEFAULTS"
mkdir -p "$PANDOC_TEMPLATES"

# Deploy profile (expand ~ to $HOME for Pandoc compatibility)
echo "[2/2] Deploying invoice profile and header..."
sed "s|~/|$HOME/|g" "$SCRIPT_DIR/invoice.yaml" > "$PANDOC_DEFAULTS/invoice.yaml"
cp "$SCRIPT_DIR/invoice-header.tex" "$PANDOC_TEMPLATES/invoice-header.tex"

echo ""
echo "=== Deploy complete ==="
echo ""
echo "Installed files:"
echo "  $PANDOC_DEFAULTS/invoice.yaml"
echo "  $PANDOC_TEMPLATES/invoice-header.tex"
echo ""
echo "Usage: md2pdf invoice.md --profile invoice"
