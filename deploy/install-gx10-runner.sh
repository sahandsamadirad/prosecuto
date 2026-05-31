#!/usr/bin/env bash
# Install GitHub Actions self-hosted runner on Asus GX10.
# Run once, then register at: https://github.com/sahandsamadirad/prosecuto/settings/actions/runners/new
set -euo pipefail

RUNNER_DIR="${HOME}/actions-runner-gx10"
REPO="sahandsamadirad/prosecuto"
LABELS="gx10,linux,ARM64"

mkdir -p "$RUNNER_DIR"
cd "$RUNNER_DIR"

ARCH="arm64"
RUNNER_VERSION=$(curl -sL https://api.github.com/repos/actions/runner/releases/latest | grep -oP '"tag_name": "\Kv[^"]+')

if [[ ! -f ./config.sh ]]; then
  echo "Downloading runner ${RUNNER_VERSION} (${ARCH})..."
  curl -sL "https://github.com/actions/runner/releases/download/${RUNNER_VERSION}/actions-runner-linux-${ARCH}-${RUNNER_VERSION#v}.tar.gz" -o runner.tar.gz
  tar xzf runner.tar.gz && rm runner.tar.gz
fi

echo ""
echo "=== GitHub Actions runner setup ==="
echo "1. Open: https://github.com/${REPO}/settings/actions/runners/new"
echo "2. Select Linux / ARM64"
echo "3. Copy the registration token and run:"
echo ""
echo "   cd $RUNNER_DIR"
echo "   ./config.sh --url https://github.com/${REPO} --token YOUR_TOKEN --labels ${LABELS} --unattended"
echo "   sudo ./svc.sh install"
echo "   sudo ./svc.sh start"
echo ""
echo "Runner will pick up deploy jobs on push to main."
