REPO_URL="https://github.com/Rawkous/CS370_OptimizedGroceryShopping.git"
REPO_DIR="$HOME/CS370_OptimizedGroceryShopping"
TS="$(date +%Y%m%d-%H%M%S)"
ENV_BK="$HOME/.env.CS370.$TS"

# 0) If a venv is active, deactivate so deletes don’t get messy
[ -n "${VIRTUAL_ENV-}" ] && deactivate || true

# 1) Backup existing .env if present
if [ -f "$REPO_DIR/.env" ]; then
  cp "$REPO_DIR/.env" "$ENV_BK"
  echo "🔹 Backed up .env → $ENV_BK"
fi

# 2) Remove old repo
rm -rf "$REPO_DIR"
echo "🧹 Removed $REPO_DIR"

# 3) Ensure tools
sudo apt-get update -y
sudo apt-get install -y git python3-venv

# 4) Clone fresh
git clone "$REPO_URL" "$REPO_DIR"
cd "$REPO_DIR"
echo "✅ Cloned $REPO_URL"

# 5) Restore or create .env
if [ -f "$ENV_BK" ] && [ ! -f ".env" ]; then
  cp "$ENV_BK" .env
  echo "✅ Restored .env from backup"
elif [ -f ".env.example" ] && [ ! -f ".env" ]; then
  cp .env.example .env
  echo "📝 Copied .env.example → .env (fill in if needed)"
fi

# 6) Python env + deps
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
pip install -r requirements.txt
# Ensure requests is present for Kroger calls
pip install -q "requests>=2.31"

echo
echo "🎯 Quick Kroger sanity tests:"
echo "  1) Token:        python -m app.cli kroger-token"
echo "  2) Locations:    python -m app.cli kroger-locations --lat 38.34 --lon -122.68 --radius 15"
echo "  3) Products:     python -m app.cli kroger-products --loc <LOCATION_ID> --term milk --limit 5"
echo "  4) End-to-end:   python -m app.cli kroger-check --lat 38.34 --lon -122.68 --radius 15 --items 'milk,eggs,bread'"
echo
echo "🚀 Start the web app when ready:"
echo "  python -m app.cli web"
# ==== end script ====
