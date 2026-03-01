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
  # ── Python core ──────────────────────────────────────────
  ms-python.python                        # Language support, virtualenvs, debugging
  ms-python.vscode-pylance                # Type checking, IntelliSense, go-to-definition
  ms-python.debugpy                       # Python debugger (attach to Emily, API, tests)
  charliermarsh.ruff                      # Ruff linter + formatter (matches pyproject.toml)
  tamasfe.even-better-toml                # pyproject.toml syntax highlighting

  # ── Testing ──────────────────────────────────────────────
  littlefoxteam.vscode-python-test-adapter # pytest integration in sidebar

  # ── Docker & containers ─────────────────────────────────
  ms-azuretools.vscode-docker             # Docker Compose, container management

  # ── Error visibility ────────────────────────────────────
  usernamehw.errorlens                    # Inline lint/error highlights (critical for ruff + mypy)

  # ── Git ──────────────────────────────────────────────────
  eamodio.gitlens                         # Blame, history, branch comparison
  mhutchie.git-graph                      # Visual branch graph

  # ── Productivity ─────────────────────────────────────────
  gruntfuggly.todo-tree                   # Find TODO/FIXME/HACK across codebase
  christian-kohler.path-intellisense      # Auto-complete file paths
  streetsidesoftware.code-spell-checker   # Catch typos in comments/strings
  editorconfig.editorconfig               # Enforce .editorconfig settings

  # ── Docs / data ─────────────────────────────────────────
  yzhang.markdown-all-in-one              # Markdown preview (ARCHITECTURE.md, DECISIONS.md)
  bierner.markdown-mermaid                # Mermaid diagrams in markdown
  redhat.vscode-yaml                      # config.yaml validation
  mechatroner.rainbow-csv                 # CSV/TSV data file viewing

  # ── API development ─────────────────────────────────────
  rangav.vscode-thunder-client            # REST client for testing Emily API endpoints
  humao.rest-client                       # HTTP file-based API testing (.http files)

  # ── Database ─────────────────────────────────────────────
  alexcvzz.vscode-sqlite                  # Browse episodes.db, knowledge.db, vault.db

  # ── Remote / advanced ───────────────────────────────────
  ms-python.mypy-type-checker             # Mypy integration (strict mode in pyproject.toml)
)

echo "Using: $CLI"
for ext in "${EXTENSIONS[@]}"; do
  echo "Installing $ext ..."
  "$CLI" --install-extension "$ext" --force || true
done
echo "Done."
