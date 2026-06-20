#!/usr/bin/env python3
"""
TITAN Project Packager
=======================
Creates 4 downloadable ZIPs containing the latest project state:
  - TITAN_SPLIT_1.zip: Context + Docs (master context, worklog, manifest, etc.)
  - TITAN_SPLIT_2.zip: Production Code (titan/ — 39 modules + recovery subpackage + tests)
  - TITAN_SPLIT_3.zip: Real Data (Dukascopy + Exness + ICMarkets + Pepperstone + Yahoo)
  - TITAN_SPLIT_4.zip: Scripts + Audit Reports (download/ + scripts/)

Excludes: .git/, __pycache__/, *.pyc, upload/, partial files
"""
import os
import zipfile
import hashlib
import json
import time
from pathlib import Path
from datetime import datetime

PROJECT = Path("/home/z/my-project")
UPLOAD = PROJECT / "upload"
UPLOAD.mkdir(exist_ok=True)

# What to exclude from every ZIP
EXCLUDE_DIRS = {".git", "__pycache__", ".pytest_cache", "upload", ".partial"}
EXCLUDE_EXTS = {".pyc", ".pyo", ".log", ".out"}
EXCLUDE_FILES = {".DS_Store", "Thumbs.db"}


def should_exclude(path: Path) -> bool:
    parts = path.parts
    for part in parts:
        if part in EXCLUDE_DIRS:
            return True
    if path.suffix in EXCLUDE_EXTS:
        return True
    if path.name in EXCLUDE_FILES:
        return True
    return False


def should_exclude_for_zip2(path: Path) -> bool:
    """For ZIP 2 (production code), exclude titan/data/ to avoid duplication."""
    if should_exclude(path):
        return True
    # Exclude anything inside titan/data/
    parts = path.parts
    if "titan" in parts:
        titan_idx = parts.index("titan")
        if titan_idx + 1 < len(parts) and parts[titan_idx + 1] == "data":
            return True
    return False


def add_to_zip(zipf: zipfile.ZipFile, project_root: Path, rel_path: str,
               compress_type=zipfile.ZIP_DEFLATED, compresslevel=6,
               exclude_fn=None):
    """Add a file or directory to the zip with compression."""
    if exclude_fn is None:
        exclude_fn = should_exclude
    abs_path = project_root / rel_path
    if not abs_path.exists():
        return 0
    count = 0
    if abs_path.is_file():
        if exclude_fn(abs_path):
            return 0
        zipf.write(abs_path, rel_path, compress_type=compress_type,
                   compresslevel=compresslevel)
        return 1
    for root, dirs, files in os.walk(abs_path):
        # Filter dirs in-place (also exclude titan/data for zip2)
        new_dirs = []
        for d in dirs:
            dpath = Path(root) / d
            if d in EXCLUDE_DIRS:
                continue
            if exclude_fn(dpath):
                continue
            new_dirs.append(d)
        dirs[:] = new_dirs
        for f in files:
            fpath = Path(root) / f
            if exclude_fn(fpath):
                continue
            if f in EXCLUDE_FILES or fpath.suffix in EXCLUDE_EXTS:
                continue
            arcname = str(fpath.relative_to(project_root))
            zipf.write(fpath, arcname, compress_type=compress_type,
                       compresslevel=compresslevel)
            count += 1
    return count


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def build_zip(zip_name: str, paths_to_add: list[str], description: str) -> dict:
    """Build one ZIP file. Returns manifest dict."""
    zip_path = UPLOAD / zip_name
    if zip_path.exists():
        zip_path.unlink()

    print(f"\n{'='*70}")
    print(f"Building {zip_name}")
    print(f"  Description: {description}")
    print(f"  Sources: {paths_to_add}")
    print(f"{'='*70}")

    t0 = time.time()
    file_count = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED,
                         compresslevel=6) as zf:
        for rel in paths_to_add:
            n = add_to_zip(zf, PROJECT, rel)
            file_count += n
            print(f"  + {rel}: {n} files")

    size_bytes = zip_path.stat().st_size
    size_mb = size_bytes / (1024 * 1024)
    sha = sha256_file(zip_path)
    elapsed = time.time() - t0

    print(f"\n  Done: {file_count} files, {size_mb:.1f} MB, {elapsed:.1f}s")
    print(f"  SHA-256: {sha}")

    return {
        "zip_name": zip_name,
        "description": description,
        "file_count": file_count,
        "size_bytes": size_bytes,
        "size_mb": round(size_mb, 2),
        "sha256": sha,
        "build_time": datetime.now().isoformat(),
        "elapsed_s": round(elapsed, 2),
        "paths_included": paths_to_add,
    }


def main():
    print("=" * 70)
    print("TITAN Project Packager — v5.0")
    print(f"Build time: {datetime.now().isoformat()}")
    print("=" * 70)
    print(f"Project root: {PROJECT}")
    print(f"Output dir:   {UPLOAD}")

    manifests = []

    # ZIP 1: Context + Docs
    m1 = build_zip(
        "TITAN_SPLIT_1.zip",
        [
            "TITAN_MASTER_CONTEXT.md",
            "MASTER_PROJECT_MANIFEST.md",
            "PROJECT_CONTEXT.md",
            "PROJECT_RECOVERY_GUIDE.md",
            "FILE_CHECKSUM_REPORT.md",
            "project_memory.md",
            "worklog.md",
            ".cursorrules",
            ".gitignore",
        ],
        "Master context + worklog + manifest + recovery guide + memory"
    )
    manifests.append(m1)

    # ZIP 2: Production Code (titan/) — EXCLUDES titan/data/ (goes in ZIP 3)
    print("\n=== Building TITAN_SPLIT_2.zip (excluding titan/data/) ===")
    zip2_path = UPLOAD / "TITAN_SPLIT_2.zip"
    if zip2_path.exists():
        zip2_path.unlink()
    file_count_2 = 0
    t0 = time.time()
    with zipfile.ZipFile(zip2_path, "w", zipfile.ZIP_DEFLATED,
                         compresslevel=6) as zf:
        file_count_2 = add_to_zip(zf, PROJECT, "titan/",
                                  exclude_fn=should_exclude_for_zip2)
    size_bytes_2 = zip2_path.stat().st_size
    size_mb_2 = size_bytes_2 / (1024 * 1024)
    sha_2 = sha256_file(zip2_path)
    elapsed_2 = time.time() - t0
    print(f"  + titan/ (excluding titan/data/): {file_count_2} files")
    print(f"  Done: {file_count_2} files, {size_mb_2:.1f} MB, {elapsed_2:.1f}s")
    print(f"  SHA-256: {sha_2}")
    m2 = {
        "zip_name": "TITAN_SPLIT_2.zip",
        "description": "Production codebase (39 modules + recovery subpackage + tests + config) — EXCLUDES titan/data/",
        "file_count": file_count_2,
        "size_bytes": size_bytes_2,
        "size_mb": round(size_mb_2, 2),
        "sha256": sha_2,
        "build_time": datetime.now().isoformat(),
        "elapsed_s": round(elapsed_2, 2),
        "paths_included": ["titan/ (excluding titan/data/)"],
    }
    manifests.append(m2)

    # ZIP 3: Real Data (titan/data/)
    m3 = build_zip(
        "TITAN_SPLIT_3.zip",
        ["titan/data/"],
        "Real XAUUSD historical data — Dukascopy + Exness + ICMarkets + Pepperstone + Yahoo GLD"
    )
    manifests.append(m3)

    # ZIP 4: Scripts + Audit Reports
    m4 = build_zip(
        "TITAN_SPLIT_4.zip",
        ["scripts/", "download/"],
        "Generation scripts + audit reports (PDFs + JSONs + diagrams)"
    )
    manifests.append(m4)

    # Build manifest
    total_files = sum(m["file_count"] for m in manifests)
    total_bytes = sum(m["size_bytes"] for m in manifests)
    total_mb = total_bytes / (1024 * 1024)

    overall = {
        "package_version": "v5.0",
        "build_time": datetime.now().isoformat(),
        "project_root": str(PROJECT),
        "total_zips": len(manifests),
        "total_files": total_files,
        "total_size_bytes": total_bytes,
        "total_size_mb": round(total_mb, 2),
        "zips": manifests,
        "notes": [
            "Each ZIP is self-contained and can be extracted independently.",
            "Extract all 4 ZIPs into the same target directory to reconstruct the project.",
            "Excludes: .git/, __pycache__/, *.pyc, *.log, *.out, .partial/",
            "Real data ZIP (TITAN_SPLIT_3.zip) contains 5 sources: Dukascopy, Exness MT5, ICMarkets MT5, Pepperstone, Yahoo GLD.",
            "Production code ZIP (TITAN_SPLIT_2.zip) excludes titan/data/ to avoid duplication with TITAN_SPLIT_3.zip.",
        ],
        "audit_history_summary": {
            "real_data_audit_v3.0": "REAL_DATA_VERIFIED (100.15% coverage)",
            "real_data_evidence_v1.0": "DATA_CLAIM_REJECTED (strict real 25.03% < 95%)",
            "production_recovery_v1.0": "RECOVERY_VERIFIED (18/18 requirements)",
        },
    }

    manifest_path = UPLOAD / "TITAN_PACKAGE_MANIFEST_v5.0.json"
    with open(manifest_path, "w") as f:
        json.dump(overall, f, indent=2)
    print(f"\n{'='*70}")
    print(f"BUILD COMPLETE")
    print(f"{'='*70}")
    print(f"Total ZIPs:   {len(manifests)}")
    print(f"Total files:  {total_files:,}")
    print(f"Total size:   {total_mb:.2f} MB ({total_bytes:,} bytes)")
    print(f"\nFiles in {UPLOAD}:")
    for f in sorted(UPLOAD.glob("*.zip")):
        size = f.stat().st_size / (1024*1024)
        print(f"  {f.name}  ({size:.2f} MB)")
    print(f"\nManifest: {manifest_path.name}")
    print(f"\nDownload paths:")
    for f in sorted(UPLOAD.glob("*.zip")):
        print(f"  /home/z/my-project/upload/{f.name}")
    print(f"  /home/z/my-project/upload/{manifest_path.name}")


if __name__ == "__main__":
    main()
