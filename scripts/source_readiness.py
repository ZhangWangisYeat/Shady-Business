#!/usr/bin/env python3
"""Offline status report for UCLA data source manifest (no API calls or spending)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "references" / "ucla-source-manifest.json"


def main():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    print(f"{manifest['project']}: {manifest['scope']} source readiness")
    for item in manifest["sources"]:
        relative = item.get("repo_local_target")
        path = ROOT / relative if relative else None
        status = "LOCAL" if path and path.is_file() else ("REMOTE / NOT INGESTED" if relative else "REFERENCE")
        print(f"{item['priority']:<15} {item['id']:<22} {status}")
        if not item["usable_now"]:
            print(f"  rights/access check: {item['license_status']}")
    print("\nNo data were downloaded. See docs/references/ucla-source-catalog.md.")


if __name__ == "__main__":
    main()
