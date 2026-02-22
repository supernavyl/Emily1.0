#!/usr/bin/env bash
# Install Cursor/VSCode extensions useful for the Emily project (Python, tests, YAML, etc.).
# Run from project root: chmod +x install-extensions.sh && ./install-extensions.sh

set -e

if command -v cursor &>/dev/null; then
  CLI=cursor
elif [ -x "$HOME/cursor/bin/cursor" ]; then
  CLI="$HOME/cursor/bin/cursor"
elif command -v code &>/dev/null; then
  CLI=code
else
  echo "Neither 'cursor' nor 'code' found in PATH or ~/cursor/. Install Cursor/VS Code CLI first." >&2
  exit 1
fi

EXTENSIONS=(
  ms-python.python
  ms-python.vscode-pylance
  ms-python.debugpy
  littlefoxteam.vscode-python-test-adapter
  yzhang.markdown-all-in-one
  redhat.vscode-yaml
  eamodio.gitlens
  editorconfig.editorconfig
)

echo "Using: $CLI"
for ext in "${EXTENSIONS[@]}"; do
  echo "Installing $ext ..."
  "$CLI" --install-extension "$ext" --force || true
done
echo "Done."
