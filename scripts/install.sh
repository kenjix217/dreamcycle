#!/usr/bin/env bash
set -euo pipefail

REPO="${DREAMCYCLE_REPO:-kenjix217/dreamcycle}"
RAW_INSTALL_URL="${DREAMCYCLE_INSTALL_URL:-https://raw.githubusercontent.com/${REPO}/main/scripts/install.sh}"
INSTALL_DIR="${DREAMCYCLE_HOME:-$HOME/.dreamcycle}"
BIN_DIR="${DREAMCYCLE_BIN_DIR:-$HOME/.local/bin}"
EXTRAS="${DREAMCYCLE_EXTRAS:-server,embeddings,sdk}"
VERSION="latest"
FROM_BUNDLE=0

usage() {
  cat <<'EOF'
DreamCycle installer

Usage:
  curl -fsSL https://raw.githubusercontent.com/kenjix217/dreamcycle/main/scripts/install.sh | bash

Options:
  --version <vX.Y.Z|X.Y.Z>  Install a specific GitHub Release version
  --install-dir <path>      Installation root (default: ~/.dreamcycle)
  --bin-dir <path>          Command wrapper directory (default: ~/.local/bin)
  --extras <names>          Python extras to install (default: server,embeddings,sdk)
  --core                    Install core DreamCycle without extras
  --from-bundle             Internal: install from an extracted release bundle
  -h, --help                Show help

Environment:
  DREAMCYCLE_HOME
  DREAMCYCLE_BIN_DIR
  DREAMCYCLE_EXTRAS
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --version)
      VERSION="${2:?missing version}"
      shift 2
      ;;
    --install-dir)
      INSTALL_DIR="${2:?missing install dir}"
      shift 2
      ;;
    --bin-dir)
      BIN_DIR="${2:?missing bin dir}"
      shift 2
      ;;
    --extras)
      EXTRAS="${2:-}"
      shift 2
      ;;
    --core)
      EXTRAS=""
      shift
      ;;
    --upgrade)
      shift
      ;;
    --from-bundle)
      FROM_BUNDLE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "DreamCycle installer requires '$1'." >&2
    exit 1
  fi
}

platform_id() {
  local os arch
  os="$(uname -s)"
  arch="$(uname -m)"
  case "$os" in
    Linux) os="linux" ;;
    Darwin) os="macos" ;;
    *)
      echo "unsupported OS: $os" >&2
      exit 1
      ;;
  esac
  case "$arch" in
    x86_64|amd64) arch="x86_64" ;;
    arm64|aarch64) arch="arm64" ;;
    *)
      echo "unsupported CPU architecture: $arch" >&2
      exit 1
      ;;
  esac
  printf '%s-%s\n' "$os" "$arch"
}

resolve_tag() {
  if [ "$VERSION" != "latest" ]; then
    case "$VERSION" in
      v*) printf '%s\n' "$VERSION" ;;
      *) printf 'v%s\n' "$VERSION" ;;
    esac
    return
  fi
  python3 - "$REPO" <<'PY'
import json
import sys
import urllib.request

repo = sys.argv[1]
url = f"https://api.github.com/repos/{repo}/releases/latest"
try:
    with urllib.request.urlopen(url, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
except Exception as exc:
    raise SystemExit(f"could not resolve latest DreamCycle release: {exc}")
tag = payload.get("tag_name")
if not tag:
    raise SystemExit("latest DreamCycle release did not include tag_name")
print(tag)
PY
}

download_and_reexec() {
  require_command curl
  require_command tar
  require_command python3
  local platform tag version asset url tmp extracted
  platform="$(platform_id)"
  tag="$(resolve_tag)"
  version="${tag#v}"
  asset="dreamcycle-${version}-${platform}.tar.gz"
  url="https://github.com/${REPO}/releases/download/${tag}/${asset}"
  tmp="$(mktemp -d)"
  echo "Downloading ${asset} from ${tag}..."
  curl -fsSL "$url" -o "$tmp/$asset"
  tar -xzf "$tmp/$asset" -C "$tmp"
  extracted="$tmp/dreamcycle-${version}-${platform}"
  exec bash "$extracted/install.sh" \
    --from-bundle \
    --version "$tag" \
    --install-dir "$INSTALL_DIR" \
    --bin-dir "$BIN_DIR" \
    --extras "$EXTRAS"
}

bundle_dir() {
  local source="${BASH_SOURCE[0]}"
  cd "$(dirname "$source")" >/dev/null 2>&1
  pwd
}

install_from_bundle() {
  require_command python3
  local bundle wheel version extras_spec venv_python dashboard_src dashboard_dst
  bundle="$(bundle_dir)"
  wheel="$(find "$bundle/wheels" -maxdepth 1 -name 'dreamcycle-*-py3-none-any.whl' | sort | tail -n 1)"
  if [ -z "$wheel" ] || [ ! -f "$wheel" ]; then
    echo "DreamCycle wheel is missing from bundle." >&2
    exit 1
  fi
  version="$(cat "$bundle/VERSION" 2>/dev/null || basename "$wheel" | sed -E 's/^dreamcycle-([0-9][^-]+)-.*$/\1/')"
  dashboard_src="$bundle/dashboard"
  dashboard_dst="$INSTALL_DIR/dashboard"

  mkdir -p "$INSTALL_DIR" "$BIN_DIR"
  python3 -m venv "$INSTALL_DIR/venv"
  venv_python="$INSTALL_DIR/venv/bin/python"
  "$venv_python" -m pip install --upgrade pip
  extras_spec=""
  if [ -n "$EXTRAS" ]; then
    extras_spec="[$EXTRAS]"
  fi
  "$venv_python" -m pip install --upgrade "${wheel}${extras_spec}"

  if [ -d "$dashboard_src/dist" ]; then
    rm -rf "$dashboard_dst"
    mkdir -p "$dashboard_dst"
    cp -R "$dashboard_src/dist" "$dashboard_dst/dist"
    cp "$dashboard_src/server.py" "$dashboard_dst/server.py"
    chmod +x "$dashboard_dst/server.py"
  fi

  write_wrappers "$version"
  "$venv_python" - <<'PY'
import dreamcycle
print(f"DreamCycle import ok: {dreamcycle.__version__}")
PY

  cat <<EOF

DreamCycle ${version} installed.

Commands:
  dreamcycle-server
  dreamcycle-hermes
  dreamcycle-dashboard
  dreamcycle-update

Install root:
  ${INSTALL_DIR}

Command wrappers:
  ${BIN_DIR}

If those commands are not found, add this to your shell profile:
  export PATH="${BIN_DIR}:\$PATH"
EOF
}

write_wrappers() {
  local version="$1"
  cat > "$BIN_DIR/dreamcycle-server" <<EOF
#!/usr/bin/env bash
exec "${INSTALL_DIR}/venv/bin/dreamcycle-server" "\$@"
EOF
  cat > "$BIN_DIR/dreamcycle-hermes" <<EOF
#!/usr/bin/env bash
exec "${INSTALL_DIR}/venv/bin/dreamcycle-hermes" "\$@"
EOF
  cat > "$BIN_DIR/dreamcycle-dashboard" <<EOF
#!/usr/bin/env bash
exec "${INSTALL_DIR}/venv/bin/python" "${INSTALL_DIR}/dashboard/server.py" "\$@"
EOF
  cat > "$BIN_DIR/dreamcycle-update" <<EOF
#!/usr/bin/env bash
set -euo pipefail
curl -fsSL "${RAW_INSTALL_URL}" | DREAMCYCLE_HOME="${INSTALL_DIR}" DREAMCYCLE_BIN_DIR="${BIN_DIR}" DREAMCYCLE_EXTRAS="${EXTRAS}" bash -s -- --upgrade
EOF
  chmod +x "$BIN_DIR/dreamcycle-server" "$BIN_DIR/dreamcycle-hermes" "$BIN_DIR/dreamcycle-dashboard" "$BIN_DIR/dreamcycle-update"
  echo "$version" > "$INSTALL_DIR/VERSION"
}

if [ "$FROM_BUNDLE" -eq 1 ] || [ -d "$(bundle_dir)/wheels" ]; then
  install_from_bundle
else
  download_and_reexec
fi
