"""Download a resumable, checksummed OQMD OPTIMADE cache for XERUS."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import random
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
BLIND_ZIP = (
    ROOT
    / "fig4/benchmark/datasets/atomly_core_v3/native_blind_package_v3.zip"
)
DEFAULT_OUTPUT = ROOT / "fig4/benchmark/server_transfer/xerus_oqmd_cache_v3"
BASE_URL = "https://oqmd.org/optimade/v1/structures"
RESPONSE_FIELDS = (
    "cartesian_site_positions,species,elements,nelements,species_at_sites,"
    "lattice_vectors,last_modified,elements_ratios,chemical_formula_descriptive,"
    "chemical_formula_reduced,chemical_formula_anonymous,nperiodic_dimensions,"
    "nsites,structure_features,dimension_types"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample-id", action="append", default=[])
    parser.add_argument("--system", action="append", default=[])
    parser.add_argument("--all-samples", action="store_true")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--page-limit", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--attempts", type=int, default=12)
    parser.add_argument("--base-delay", type=float, default=8.0)
    parser.add_argument("--max-delay", type=float, default=120.0)
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of element systems to download concurrently.",
    )
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_bytes(payload)
    os.replace(temporary, path)


def read_samples() -> list[dict[str, str]]:
    with zipfile.ZipFile(BLIND_ZIP) as archive:
        names = [name for name in archive.namelist() if name.endswith("sample_manifest.csv")]
        if len(names) != 1:
            raise RuntimeError("Expected one sample_manifest.csv in blind package")
        with archive.open(names[0]) as raw:
            return list(csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8")))


def xerus_systems(elements: list[str]) -> set[str]:
    """Reproduce XERUS subset systems, excluding its O and C-O special cases."""
    systems = set()
    ordered = sorted(elements)
    for size in range(1, len(ordered) + 1):
        for subset in combinations(ordered, size):
            key = "-".join(subset)
            if key not in {"O", "C-O"}:
                systems.add(key)
    return systems


def selected_systems(args: argparse.Namespace) -> tuple[list[str], list[str]]:
    samples = read_samples()
    requested = set(args.sample_id)
    known = {row["sample_id"] for row in samples}
    unknown = requested - known
    if unknown:
        raise ValueError(f"Unknown sample IDs: {', '.join(sorted(unknown))}")
    selected = samples if args.all_samples else [
        row for row in samples if row["sample_id"] in requested
    ]
    systems = {"-".join(sorted(system.split("-"))) for system in args.system}
    for row in selected:
        systems.update(xerus_systems(row["sample_elements"].split(";")))
    if not systems:
        raise ValueError("Select --sample-id, --system, or --all-samples")
    return sorted(systems), sorted(row["sample_id"] for row in selected)


def initial_url(system: str, page_limit: int) -> str:
    elements = system.split("-")
    filter_value = (
        "elements HAS ONLY "
        + ",".join(f'"{element}"' for element in elements)
        + " AND _oqmd_stability<0.05"
    )
    query = urllib.parse.urlencode(
        {
            "filter": filter_value,
            "response_fields": RESPONSE_FIELDS,
            "page_limit": page_limit,
        }
    )
    return f"{BASE_URL}?{query}"


def normalize_next_url(value: object) -> str | None:
    if isinstance(value, dict):
        value = value.get("href")
    if not value:
        return None
    url = str(value)
    if url.startswith("http://oqmd.org/"):
        url = "https://" + url.removeprefix("http://")
    return url


def validate_page(payload: bytes, expected_system: str) -> dict:
    data = json.loads(payload)
    if not isinstance(data.get("data"), list) or not isinstance(data.get("meta"), dict):
        raise ValueError("Invalid OPTIMADE page")
    if data["meta"].get("provider", {}).get("prefix", "").lower() != "oqmd":
        raise ValueError("Response is not from OQMD")
    expected = set(expected_system.split("-"))
    for entry in data["data"]:
        elements = set(entry.get("attributes", {}).get("elements", []))
        if elements != expected:
            raise ValueError(
                f"Element mismatch for {entry.get('id')}: {sorted(elements)} != {sorted(expected)}"
            )
    return data


def fetch_page(url: str, args: argparse.Namespace, system: str) -> tuple[bytes, dict, int]:
    headers = {"User-Agent": "xrd-native-benchmark-oqmd-cache/3.0"}
    context = ssl.create_default_context()
    last_error: Exception | None = None
    for attempt in range(1, args.attempts + 1):
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(
                request, timeout=args.timeout, context=context
            ) as response:
                if response.status != 200:
                    raise RuntimeError(f"HTTP {response.status}")
                payload = response.read()
            return payload, validate_page(payload, system), attempt
        except (
            OSError,
            RuntimeError,
            TimeoutError,
            ValueError,
            json.JSONDecodeError,
            urllib.error.HTTPError,
            urllib.error.URLError,
        ) as error:
            last_error = error
            if attempt == args.attempts:
                break
            delay = min(args.max_delay, args.base_delay * (2 ** min(attempt - 1, 4)))
            delay += random.uniform(0, min(5.0, delay * 0.1))
            print(
                f"{system}: attempt {attempt}/{args.attempts} failed: {error}; "
                f"retrying in {delay:.1f} s",
                flush=True,
            )
            time.sleep(delay)
    raise RuntimeError(f"{system}: exhausted retries for {url}: {last_error}")


def complete_manifest_valid(system_root: Path, manifest: dict, system: str) -> bool:
    ids = []
    for page in manifest.get("pages", []):
        path = system_root / page["file"]
        if not path.exists() or sha256_path(path) != page.get("sha256"):
            return False
        try:
            data = validate_page(path.read_bytes(), system)
        except (ValueError, json.JSONDecodeError):
            return False
        ids.extend(str(entry["id"]) for entry in data["data"])
    return (
        len(ids) == len(set(ids))
        and len(ids) == int(manifest.get("entry_count", -1))
    )


def quarantine_system_cache(system_root: Path, output_root: Path) -> Path:
    quarantine_root = output_root.parent / f"{output_root.name}_quarantine"
    quarantine_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = quarantine_root / f"{system_root.name}_{timestamp}"
    os.replace(system_root, target)
    print(f"{system_root.name}: quarantined stale system cache at {target}", flush=True)
    return target


def download_system(system: str, output_root: Path, args: argparse.Namespace) -> dict:
    system_root = output_root / "systems" / system
    manifest_path = system_root / "manifest.json"
    if manifest_path.exists():
        try:
            previous = json.loads(manifest_path.read_text())
        except (OSError, json.JSONDecodeError):
            previous = {}
        if previous.get("complete") is True:
            if complete_manifest_valid(system_root, previous, system):
                print(f"{system}: complete cache exists; skipped", flush=True)
                return previous
    if system_root.exists():
        # Never mix pages from different runs or page limits. A system without a
        # valid complete manifest is rebuilt atomically at system granularity.
        quarantine_system_cache(system_root, output_root)

    pages = []
    ids = []
    url = initial_url(system, args.page_limit)
    page_index = 0
    while url:
        relative = Path("pages") / f"page_{page_index:04d}.json"
        page_path = system_root / relative
        payload, data, attempts = fetch_page(url, args, system)
        page_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = page_path.with_suffix(".json.partial")
        temporary.write_bytes(payload)
        os.replace(temporary, page_path)
        page_ids = [str(entry["id"]) for entry in data["data"]]
        ids.extend(page_ids)
        pages.append(
            {
                "file": str(relative),
                "request_url": url,
                "sha256": sha256_bytes(payload),
                "entry_count": len(page_ids),
                "request_attempts": attempts,
                "server_timestamp": data["meta"].get("time_stamp"),
            }
        )
        print(
            f"{system}: page {page_index + 1}, {len(page_ids)} entries, "
            f"{attempts} attempt(s)",
            flush=True,
        )
        url = normalize_next_url(data.get("links", {}).get("next"))
        page_index += 1

    if len(ids) != len(set(ids)):
        raise RuntimeError(f"Duplicate OQMD IDs across pages for {system}")
    manifest = {
        "schema_version": 1,
        "provider": "OQMD OPTIMADE",
        "provider_base_url": BASE_URL,
        "protocol": "elements HAS ONLY <system> AND _oqmd_stability<0.05",
        "system": system,
        "elements": system.split("-"),
        "page_limit": args.page_limit,
        "complete": True,
        "completed_at_utc": utc_now(),
        "entry_count": len(ids),
        "database_ids": ids,
        "pages": pages,
    }
    write_json_atomic(manifest_path, manifest)
    return manifest


def main() -> None:
    args = parse_args()
    if (
        args.page_limit <= 0
        or args.attempts <= 0
        or args.timeout <= 0
        or args.workers <= 0
    ):
        raise ValueError("page-limit, attempts, timeout, and workers must be positive")
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    systems, sample_ids = selected_systems(args)
    failures = []
    manifests = []

    def save_cache_manifest(complete: bool) -> None:
        cache_manifest = {
            "schema_version": 1,
            "created_or_updated_at_utc": utc_now(),
            "blind_package": str(BLIND_ZIP.relative_to(ROOT)),
            "blind_package_sha256": sha256_path(BLIND_ZIP),
            "selected_sample_ids": sample_ids,
            "requested_system_count": len(systems),
            "complete_system_count": len(manifests),
            "failed_system_count": len(failures),
            "complete": complete,
            "systems": [
                {
                    "system": manifest["system"],
                    "entry_count": manifest["entry_count"],
                    "manifest": f"systems/{manifest['system']}/manifest.json",
                    "manifest_sha256": sha256_path(
                        output_root
                        / f"systems/{manifest['system']}/manifest.json"
                    ),
                }
                for manifest in sorted(manifests, key=lambda item: item["system"])
            ],
            "failures": sorted(failures, key=lambda item: item["system"]),
        }
        write_json_atomic(output_root / "cache_manifest.json", cache_manifest)

    # Mark the cache incomplete before adding systems so an interrupted build
    # can never be mistaken for a frozen input snapshot.
    save_cache_manifest(False)
    def run_one(index: int, system: str) -> dict:
        print(f"[{index}/{len(systems)}] {system}", flush=True)
        return download_system(system, output_root, args)

    if args.workers == 1:
        for index, system in enumerate(systems, start=1):
            try:
                manifests.append(run_one(index, system))
            except Exception as error:  # keep other systems resumable
                failures.append({"system": system, "error": str(error)})
                print(f"{system}: FAILED: {error}", flush=True)
            save_cache_manifest(False)
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            pending = {
                executor.submit(run_one, index, system): system
                for index, system in enumerate(systems, start=1)
            }
            for future in as_completed(pending):
                system = pending[future]
                try:
                    manifests.append(future.result())
                except Exception as error:  # keep other systems resumable
                    failures.append({"system": system, "error": str(error)})
                    print(f"{system}: FAILED: {error}", flush=True)
                save_cache_manifest(False)
    complete = not failures and len(manifests) == len(systems)
    save_cache_manifest(complete)
    print(
        f"Cache status: {len(manifests)}/{len(systems)} systems complete at {output_root}",
        flush=True,
    )
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
