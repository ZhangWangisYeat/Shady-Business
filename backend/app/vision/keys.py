"""API keys for the vision scripts, from the environment or a gitignored .env file."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
# backend/.env first, then mobile/.env, which already holds the app's keys.
# expo only bundles variables starting with EXPO_PUBLIC_ into the app, so
# keys kept there for these scripts never end up inside the apk.
ENV_FILES = (ROOT / "backend" / ".env", ROOT / "mobile" / ".env")


# a key set in one terminal window isn't visible to commands run anywhere
# else, so the scripts also read the .env files (gitignored, like every .env).
# a real environment variable still wins over a file, and the first file wins
# over the second.
def load_keys(paths=ENV_FILES) -> None:
    for path in [paths] if isinstance(paths, Path) else paths:
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            os.environ.setdefault(name.strip(), value.strip().strip('"').strip("'"))
