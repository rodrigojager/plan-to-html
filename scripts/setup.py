#!/usr/bin/env python3
"""Install isolated, pinned renderer dependencies. No global package changes."""
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import subprocess
import shutil
import sys
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
MERMAID_VERSION = "12.2.0"
ESBUILD_VERSION = "0.28.2"
FONT_VERSION = "5.3.0"


def install_fonts():
    target = ROOT / "assets" / "fonts"
    target.mkdir(parents=True, exist_ok=True)
    for family, weights in [("inter", [400, 600, 700]), ("jetbrains-mono", [400, 600]),
                            ("source-serif-4", [400, 600]), ("dm-sans", [400, 600, 700]),
                            ("ibm-plex-sans", [400, 600]), ("caveat", [400, 700]),
                            ("kalam", [400, 700]), ("cinzel", [600]),
                            ("im-fell-english", [400]), ("bebas-neue", [400]),
                            ("libre-baskerville", [400, 700]), ("rajdhani", [600, 700])]:
        filenames = [f"{family}-latin-{weight}-normal.woff2" for weight in weights]
        license_name = family + "-LICENSE.txt"
        if all((target / name).is_file() for name in filenames + [license_name]):
            continue
        with urllib.request.urlopen(f"https://registry.npmjs.org/@fontsource/{family}/{FONT_VERSION}", timeout=45) as response:
            metadata = json.load(response)
        with urllib.request.urlopen(metadata["dist"]["tarball"], timeout=60) as response:
            payload = response.read()
        algorithm, expected = metadata["dist"]["integrity"].split("-", 1)
        if base64.b64encode(hashlib.new(algorithm, payload).digest()).decode() != expected:
            raise RuntimeError("Font package integrity mismatch: " + family)
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
            for name in filenames:
                (target / name).write_bytes(archive.extractfile("package/files/" + name).read())
            (target / license_name).write_bytes(archive.extractfile("package/LICENSE").read())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-mermaid", action="store_true")
    parser.add_argument("--with-js-bundler", action="store_true", help="Also install isolated esbuild for ES module imports")
    args = parser.parse_args()
    subprocess.run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
                    "--no-warn-script-location", "--upgrade", "--target", str(ROOT / ".vendor"),
                    "-r", str(ROOT / "requirements.txt")], check=True)
    install_fonts()
    if args.with_js_bundler:
        npm = shutil.which("npm.cmd") or shutil.which("npm")
        if not npm:
            raise RuntimeError("Node.js/npm is required for --with-js-bundler")
        subprocess.run([npm, "install", "--prefix", str(ROOT / ".vendor" / "node"),
                        "--no-audit", "--no-fund", "--ignore-scripts", f"esbuild@{ESBUILD_VERSION}"], check=True)
    if not args.skip_mermaid:
        target = ROOT / "assets" / "vendor"
        target.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(f"https://registry.npmjs.org/mermaid/{MERMAID_VERSION}", timeout=45) as response:
            metadata = json.load(response)
        with urllib.request.urlopen(metadata["dist"]["tarball"], timeout=60) as response:
            data = response.read()
        algorithm, digest = metadata["dist"]["integrity"].split("-", 1)
        if base64.b64encode(hashlib.new(algorithm, data).digest()).decode() != digest:
            raise RuntimeError("Mermaid package integrity mismatch")
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as package:
            for source, name in [("package/dist/mermaid.min.js", "mermaid.min.js"), ("package/LICENSE", "MERMAID-LICENSE")]:
                member = package.extractfile(source)
                if member is None:
                    raise RuntimeError(f"Missing package member: {source}")
                (target / name).write_bytes(member.read())
        (target / "version.json").write_text(json.dumps({"mermaid": MERMAID_VERSION, "integrity": metadata["dist"]["integrity"]}) + "\n", encoding="utf-8", newline="\n")
    print("Plan HTML ready. Dependencies are isolated in the skill directory.")


if __name__ == "__main__":
    main()
