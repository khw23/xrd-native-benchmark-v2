"""Download a resumable, checksummed OQMD OPTIMADE cache for XERUS."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import shutil
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
BLIND_ROOT = (
    ROOT / "fig4/benchmark/datasets/atomly_core_v3/native_blind_package_v3"
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
    parser.add_argument(
        "--blind-root",
        type=Path,
        default=BLIND_ROOT,
        help="Unpacked directory containing sample_manifest.csv.",
    )
    parser.add_argument("--sample-id", action="append", default=[])
    parser.add_argument("--system", action="append", default=[])
    parser.add_argument("--all-samples", action="store_true")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--seed-root",
        type=Path,
        default=None,
        help="Optional complete cache whose matching system folders may be reused.",
    )
    parser.add_argument(
        "--audit-only",
        action="store_true",
        help="Write required-system coverage without copying or downloading pages.",
    )
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


def provenance_path(path: Path) -> str:
    """Keep repository inputs portable while retaining external absolute paths."""
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT.resolve()))
    except ValueError:
        return str(resolved)


def write_json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_bytes(payload)
    os.replace(temporary, path)


def manifest_path(blind_root: Path) -> Path:
    if blind_root.is_dir():
        path = blind_root / "sample_manifest.csv"
        if not path.exists():
            raise FileNotFoundError(f"Missing sample manifest: {path}")
        return path
    raise ValueError(
        "--blind-root must be an unpacked directory containing sample_manifest.csv"
    )


def read_samples(blind_root: Path) -> list[dict[str, str]]:
    with manifest_path(blind_root).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def xerus_system(elements: list[str]) -> str:
    """Return the one full element system passed to XERUS OptimadeQuery.

    XERUS ``multiquery`` constructs exactly one OQMD ``OptimadeQuery`` from
    the disclosed sample element list. OQMD translates its ``HAS ONLY`` query
    to containment of every listed element plus ``ntypes=len(elements)``.
    Therefore subset expansion here would not reproduce the native method and
    would create redundant API traffic.
    """
    return "-".join(sorted(set(elements)))


def selected_systems(args: argparse.Namespace) -> tuple[list[str], list[str]]:
    samples = read_samples(args.blind_root.resolve())
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
        systems.add(xerus_system(row["sample_elements"].split(";")))
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
    blind_root = args.blind_root.resolve()
    input_manifest = manifest_path(blind_root)
    output_root.mkdir(parents=True, exist_ok=True)
    systems, sample_ids = selected_systems(args)
    seed_root = args.seed_root.resolve() if args.seed_root is not None else None
    audit_rows = []
    for system in systems:
        destination_manifest = output_root / "systems" / system / "manifest.json"
        seed_manifest = (
            seed_root / "systems" / system / "manifest.json" if seed_root else None
        )
        destination_valid = False
        seed_valid = False
        if destination_manifest.exists():
            try:
                value = json.loads(destination_manifest.read_text(encoding="utf-8"))
                destination_valid = value.get("complete") is True and complete_manifest_valid(
                    destination_manifest.parent, value, system
                )
            except (OSError, ValueError, json.JSONDecodeError):
                destination_valid = False
        if seed_manifest is not None and seed_manifest.exists():
            try:
                value = json.loads(seed_manifest.read_text(encoding="utf-8"))
                seed_valid = value.get("complete") is True and complete_manifest_valid(
                    seed_manifest.parent, value, system
                )
            except (OSError, ValueError, json.JSONDecodeError):
                seed_valid = False
        audit_rows.append(
            {
                "system": system,
                "destination_complete": destination_valid,
                "seed_complete": seed_valid,
                "requires_download": not destination_valid and not seed_valid,
            }
        )
    with (output_root / "required_systems_audit.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(audit_rows[0]))
        writer.writeheader()
        writer.writerows(audit_rows)
    coverage = {
        "audit_timepoint": "before_seed_copy_and_download",
        "input_manifest": provenance_path(input_manifest),
        "input_manifest_sha256": sha256_path(input_manifest),
        "required_system_count": len(systems),
        "already_complete": sum(row["destination_complete"] for row in audit_rows),
        "reusable_from_seed": sum(row["seed_complete"] for row in audit_rows),
        "requires_download": sum(row["requires_download"] for row in audit_rows),
    }
    write_json_atomic(output_root / "coverage_audit.json", coverage)
    print(json.dumps(coverage, indent=2), flush=True)
    if args.audit_only:
        return

    if seed_root is not None:
        for row in audit_rows:
            if row["destination_complete"] or not row["seed_complete"]:
                continue
            source = seed_root / "systems" / row["system"]
            destination = output_root / "systems" / row["system"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, destination)
            print(f"{row['system']}: copied from seed cache", flush=True)
    failures = []
    manifests = []

    def save_cache_manifest(complete: bool) -> None:
        cache_manifest = {
            "schema_version": 1,
            "created_or_updated_at_utc": utc_now(),
            "blind_root": provenance_path(blind_root),
            "input_manifest": provenance_path(input_manifest),
            "input_manifest_sha256": sha256_path(input_manifest),
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
