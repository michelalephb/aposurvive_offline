"""Download source PDFs listed in corpus/sources.yaml into corpus/raw/.

Never overwrites: an existing corpus/raw/<id>.pdf is kept and only re-hashed.
Writes corpus/raw/manifest.json with sha256 and size for every document.

    python -m pipeline.fetch
"""

from __future__ import annotations

import json
import sys
import urllib.request

from .common import RAW, load_sources, sha256_file

UA = "Mozilla/5.0 (aposurvive corpus fetch)"


def fetch_all() -> dict:
    RAW.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, dict] = {}
    failed: list[str] = []
    for doc in load_sources():
        dest = RAW / f"{doc['id']}.pdf"
        if dest.exists():
            print(f"[keep] {dest.name} already present")
        else:
            print(f"[get ] {doc['id']} <- {doc['url']}")
            tmp = dest.with_suffix(".part")
            try:
                req = urllib.request.Request(doc["url"], headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=120) as r, tmp.open("wb") as f:
                    while chunk := r.read(1 << 20):
                        f.write(chunk)
                with tmp.open("rb") as f:
                    if f.read(5) != b"%PDF-":
                        raise ValueError("response is not a PDF")
                tmp.rename(dest)
            except Exception as e:  # report and continue, never fake a file
                tmp.unlink(missing_ok=True)
                print(f"[FAIL] {doc['id']}: {e}. Place the PDF at {dest} by hand.")
                failed.append(doc["id"])
                continue
        manifest[doc["id"]] = {
            "file": dest.name,
            "sha256": sha256_file(dest),
            "bytes": dest.stat().st_size,
            "url": doc["url"],
        }
    (RAW / "manifest.json").write_text(json.dumps(manifest, indent=2))
    if failed:
        print(f"\n{len(failed)} document(s) missing: {', '.join(failed)}")
    return {"manifest": manifest, "failed": failed}


if __name__ == "__main__":
    result = fetch_all()
    sys.exit(1 if result["failed"] else 0)
