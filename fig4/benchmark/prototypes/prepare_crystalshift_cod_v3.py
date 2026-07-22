"""Build CrystalShift inputs from the frozen COD front-end and public v3 data."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import re
import shutil
import tempfile
import warnings
from collections import Counter
from contextlib import redirect_stdout
from pathlib import Path

import numpy as np
import pandas as pd
from pymatgen.analysis.structure_matcher import ElementComparator, StructureMatcher
from pymatgen.core import Structure
from pymatgen.io.cif import CifFile, CifParser, CifWriter
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
from scipy import sparse
from scipy.sparse.linalg import spsolve


ROOT = Path(__file__).resolve().parents[3]
BLIND_ROOT = ROOT / "fig4/benchmark/datasets/atomly_core_v3/native_blind_package_v3"
COD_ROOT = ROOT / "fig4/benchmark/method_inputs/cod_native_v3"
OUT_ROOT = ROOT / "fig4/benchmark/method_inputs/crystalshift_cod_v3"
SNAPSHOT_ROOT = (
    ROOT
    / "fig4/benchmark/results/atomly_core_v3/crystaltree_cod_frontend/input_preparation"
)
DEFAULT_CONVERTER = (
    ROOT / "fig4/benchmark/third_party/CrystalShift.jl/src/cif_to_input_file.py"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--blind-root", type=Path, default=BLIND_ROOT)
    parser.add_argument("--cod-root", type=Path, default=COD_ROOT)
    parser.add_argument("--converter", type=Path, default=DEFAULT_CONVERTER)
    parser.add_argument("--output-root", type=Path, default=OUT_ROOT)
    parser.add_argument("--snapshot-root", type=Path, default=SNAPSHOT_ROOT)
    parser.add_argument("--limit-systems", type=int, default=None)
    parser.add_argument("--system-key", action="append", default=[])
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def system_key(elements: str) -> str:
    return "-".join(sorted(str(elements).split(";")))


def database_id(path: Path) -> str:
    match = re.search(r"\(cod_([^\)]+)\)", path.stem, flags=re.IGNORECASE)
    return match.group(1) if match else path.stem


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def crystal_system_from_number(number: int) -> str:
    if 1 <= number <= 2:
        return "triclinic"
    if number <= 15:
        return "monoclinic"
    if number <= 74:
        return "orthohombic"
    if number <= 142:
        return "tetragonal"
    if number <= 167:
        return "trigonal"
    if number <= 194:
        return "hexagonal"
    if number <= 230:
        return "cubic"
    raise ValueError(f"Invalid space-group number: {number}")


def scalar(value: object) -> str:
    if isinstance(value, list):
        value = value[0] if value else ""
    return str(value).strip().strip("'\"")


def declared_space_group(path: Path) -> tuple[str, int | None]:
    block = next(iter(CifFile.from_file(path).data.values()))
    lowered = {key.lower(): value for key, value in block.data.items()}
    symbol = ""
    for key in (
        "_space_group_name_h-m_alt",
        "_symmetry_space_group_name_h-m",
        "_cod_original_sg_symbol_h-m",
    ):
        if key in lowered:
            symbol = scalar(lowered[key])
            break
    number = None
    for key in (
        "_space_group_it_number",
        "_symmetry_int_tables_number",
    ):
        if key in lowered:
            try:
                number = int(float(scalar(lowered[key])))
            except ValueError:
                number = None
            break
    return symbol, number


def sanitize_unparseable_cif(path: Path) -> tuple[str, dict[str, object]]:
    """Remove only non-coordinate atom placeholders and invalid H metadata."""
    cif = CifFile.from_file(path)
    block = next(iter(cif.data.values()))
    atom_loop = next(
        (loop for loop in block.loops if "_atom_site_label" in loop), None
    )
    if atom_loop is None:
        raise ValueError("No atom-site loop available for structured sanitation")
    required = [
        "_atom_site_type_symbol",
        "_atom_site_fract_x",
        "_atom_site_fract_y",
        "_atom_site_fract_z",
    ]
    if any(field not in atom_loop for field in required):
        raise ValueError("Atom-site loop lacks species or fractional coordinates")
    row_count = len(block.data["_atom_site_label"])
    valid = [
        all(
            scalar(block.data[field][index]) not in {"", ".", "?"}
            for field in required
        )
        for index in range(row_count)
    ]
    removed = valid.count(False)
    for field in atom_loop:
        block.data[field] = [
            value for value, keep in zip(block.data[field], valid, strict=True) if keep
        ]
    dropped_attached_hydrogens = False
    attached = "_atom_site_attached_hydrogens"
    if attached in atom_loop and any(
        scalar(value) in {"", ".", "?"} for value in block.data[attached]
    ):
        atom_loop.remove(attached)
        del block.data[attached]
        dropped_attached_hydrogens = True
    if removed == 0 and not dropped_attached_hydrogens:
        raise ValueError("Structured sanitation made no permitted change")
    return str(cif), {
        "removed_noncoordinate_atom_rows": removed,
        "dropped_invalid_attached_hydrogen_column": dropped_attached_hydrogens,
    }


def parse_source_structure(path: Path) -> tuple[Structure, str, dict[str, object]]:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            structure = CifParser(path, check_cif=False).parse_structures(
                primitive=False, check_occu=False, on_error="raise"
            )[0]
        return structure, "direct_pymatgen_parse", {}
    except Exception as direct_error:
        sanitized, changes = sanitize_unparseable_cif(path)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            structure = CifParser(io.StringIO(sanitized), check_cif=False).parse_structures(
                primitive=False, check_occu=False, on_error="raise"
            )[0]
        changes["direct_parse_error_type"] = type(direct_error).__name__
        changes["direct_parse_error"] = str(direct_error)
        return structure, "structured_placeholder_cleanup", changes


def analyzed_space_group(structure: Structure) -> tuple[str, int | None, str]:
    try:
        analyzer = SpacegroupAnalyzer(structure, symprec=0.1, angle_tolerance=5)
        return (
            analyzer.get_space_group_symbol(),
            analyzer.get_space_group_number(),
            "ok",
        )
    except Exception as error:
        return "", None, f"{type(error).__name__}: {error}"


def occupancy_signature(structure: Structure) -> str:
    sites = []
    for site in structure:
        species = sorted(
            (str(specie), round(float(amount), 8))
            for specie, amount in site.species.items()
        )
        sites.append(species)
    return hashlib.sha256(repr(sorted(sites)).encode("utf-8")).hexdigest()


def structure_validation(before: Structure, after: Structure) -> dict[str, object]:
    before_cell = (*before.lattice.abc, *before.lattice.angles)
    after_cell = (*after.lattice.abc, *after.lattice.angles)
    cell_delta = max(
        abs(float(a) - float(b))
        for a, b in zip(before_cell, after_cell, strict=True)
    )
    matcher = StructureMatcher(
        primitive_cell=False,
        scale=False,
        attempt_supercell=False,
        comparator=ElementComparator(),
    )
    checks = {
        "elements_preserved": {str(e) for e in before.composition.elements}
        == {str(e) for e in after.composition.elements},
        "composition_preserved": before.composition.almost_equals(
            after.composition, rtol=1e-6, atol=1e-6
        ),
        "cell_preserved": cell_delta <= 1e-5,
        "site_count_preserved": len(before) == len(after),
        "occupancy_preserved": occupancy_signature(before)
        == occupancy_signature(after),
    }
    if before is after or before == after:
        checks["structure_match"] = True
    else:
        try:
            checks["structure_match"] = bool(matcher.fit(before, after))
        except Exception:
            checks["structure_match"] = False
    checks["cell_max_abs_delta"] = cell_delta
    checks["validation_passed"] = all(
        bool(checks[key])
        for key in (
            "elements_preserved",
            "composition_preserved",
            "cell_preserved",
            "site_count_preserved",
            "occupancy_preserved",
            "structure_match",
        )
    )
    return checks


class ConverterSystemExit(RuntimeError):
    pass


class AllConversionsFailed(RuntimeError):
    def __init__(self, attempts: list[dict[str, str]]) -> None:
        self.attempts = attempts
        super().__init__("all converter strategies failed")


def convert_one(converter: object, path: Path, output: Path) -> str:
    try:
        with redirect_stdout(io.StringIO()):
            converter.cif_to_input(
                [path], str(output), q_range=(7.0, 58.0), wvlen=1.5406
            )
    except SystemExit as error:
        raise ConverterSystemExit(f"converter raised SystemExit({error.code})") from error
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError("converter produced no output")
    return output.read_text(encoding="utf-8")


def write_normalized_cif(
    structure: Structure, output: Path, symprec: float | None
) -> None:
    writer = CifWriter(
        structure,
        symprec=symprec,
        angle_tolerance=5,
        refine_struct=False,
        significant_figures=8,
    )
    for block in writer.cif_file.data.values():
        block.max_len = 2048
    output.write_text(str(writer), encoding="utf-8")


def normalize_crystalshift_block(block: str, expected_crystal_system: str) -> str:
    """Make the unquoted CrystalShift header safe for its comma parser."""
    header, separator, remainder = block.partition("\n")
    fields = header.split(",")
    if len(fields) < 9:
        raise ValueError(f"CrystalShift header has {len(fields)} fields; expected >= 9")
    crystal_system_index = len(fields) - 7
    phase_name = "_".join(fields[1:crystal_system_index])
    if expected_crystal_system not in {
        "triclinic",
        "monoclinic",
        "orthohombic",
        "tetragonal",
        "trigonal",
        "hexagonal",
        "cubic",
    }:
        raise ValueError(
            f"Unsupported CrystalShift crystal system: {expected_crystal_system!r}"
        )
    for value in fields[crystal_system_index + 1 :]:
        float(value)
    normalized = [
        fields[0],
        phase_name,
        expected_crystal_system,
        *fields[crystal_system_index + 1 :],
    ]
    return ",".join(normalized) + separator + remainder


def converter_crystal_system(block: str) -> str:
    header = block.partition("\n")[0]
    fields = header.split(",")
    if len(fields) < 9:
        return ""
    return fields[-7]


def convert_with_fallback(
    converter: object,
    source: Path,
    structure: Structure,
    expected_crystal_system: str,
    normalized_root: Path,
) -> tuple[str, str, str, dict[str, object], list[dict[str, str]], str]:
    attempts: list[dict[str, str]] = []
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        direct_output = temp_root / "direct.csv"
        try:
            raw_block = convert_one(converter, source, direct_output)
            return (
                normalize_crystalshift_block(raw_block, expected_crystal_system),
                "official_converter_direct",
                "",
                structure_validation(structure, structure),
                attempts,
                converter_crystal_system(raw_block),
            )
        except Exception as error:
            attempts.append(
                {
                    "stage": "official_converter_direct",
                    "error_type": type(error).__name__,
                    "error": str(error),
                }
            )

        _, computed_number, _ = analyzed_space_group(structure)
        strategies: list[tuple[str, float | None]] = []
        if computed_number is not None:
            strategies.append(("pymatgen_symmetry_normalized", 0.1))
        strategies.append(("pymatgen_p1_normalized", None))
        for strategy, symprec in strategies:
            normalized = temp_root / f"{strategy}.cif"
            converted = temp_root / f"{strategy}.csv"
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    write_normalized_cif(structure, normalized, symprec)
                    roundtrip = CifParser(normalized, check_cif=False).parse_structures(
                        primitive=False, check_occu=False, on_error="raise"
                    )[0]
                validation = structure_validation(structure, roundtrip)
                if not validation["validation_passed"]:
                    raise ValueError(
                        "structure round-trip validation failed: "
                        + json.dumps(validation, sort_keys=True)
                    )
                raw_block = convert_one(converter, normalized, converted)
                normalized_root.mkdir(parents=True, exist_ok=True)
                saved = normalized_root / source.name
                shutil.copy2(normalized, saved)
                return (
                    normalize_crystalshift_block(raw_block, expected_crystal_system),
                    strategy,
                    str(saved.relative_to(ROOT)),
                    validation,
                    attempts,
                    converter_crystal_system(raw_block),
                )
            except Exception as error:
                attempts.append(
                    {
                        "stage": strategy,
                        "error_type": type(error).__name__,
                        "error": str(error),
                    }
                )
    raise AllConversionsFailed(attempts)


def baseline_asls(
    intensity: np.ndarray,
    smoothness: float = 1e7,
    asymmetry: float = 0.001,
    iterations: int = 10,
) -> np.ndarray:
    n_points = len(intensity)
    difference = sparse.diags(
        [np.ones(n_points), -2 * np.ones(n_points), np.ones(n_points)],
        [0, 1, 2],
        shape=(n_points - 2, n_points),
    )
    penalty = (smoothness * difference.T @ difference).tocsc()
    weights = np.ones(n_points)
    result = np.zeros(n_points)
    for _ in range(iterations):
        matrix = sparse.spdiags(weights, 0, n_points, n_points, format="csc")
        result = spsolve(matrix + penalty, weights * intensity)
        weights = asymmetry * (intensity > result) + (1 - asymmetry) * (
            intensity <= result
        )
    return result


def main() -> None:
    args = parse_args()
    blind_root = args.blind_root.resolve()
    cod_root = args.cod_root.resolve()
    output_root = args.output_root.resolve()
    snapshot_root = args.snapshot_root.resolve()
    if not args.converter.exists():
        raise FileNotFoundError(
            f"CrystalShift converter not found: {args.converter}. Clone CrystalShift.jl "
            "and pass --converter /path/to/CrystalShift.jl/src/cif_to_input_file.py"
        )
    spec = importlib.util.spec_from_file_location("crystalshift_converter", args.converter)
    converter = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(converter)

    manifest = pd.read_csv(blind_root / "sample_manifest.csv")
    manifest["system_key"] = manifest["sample_elements"].map(system_key)
    systems = sorted(manifest["system_key"].unique())
    if args.system_key:
        requested = set(args.system_key)
        unknown = requested.difference(systems)
        if unknown:
            raise ValueError(f"Unknown system keys: {sorted(unknown)}")
        systems = [key for key in systems if key in requested]
    if args.limit_systems is not None:
        systems = systems[: args.limit_systems]
    if output_root.exists() and any(output_root.iterdir()) and not args.resume:
        raise FileExistsError(
            f"Output directory is not empty: {output_root}. Use --resume or choose "
            "a new --output-root; existing conversion artifacts will not be overwritten."
        )
    output_root.mkdir(parents=True, exist_ok=True)

    pattern_root = output_root / "patterns_preprocessed"
    pattern_root.mkdir(exist_ok=True)
    pattern_rows = []
    for path in sorted((blind_root / "patterns").glob("*.xy")):
        raw = np.loadtxt(path)
        q_nm_inverse = (
            10.0
            * 4.0
            * np.pi
            * np.sin(np.deg2rad(raw[:, 0] / 2.0))
            / 1.5406
        )
        in_model_range = (q_nm_inverse >= 7.0) & (q_nm_inverse <= 58.0)
        cropped = raw[in_model_range]
        if len(cropped) < 2:
            raise ValueError(
                f"{path.name}: fewer than two points in CrystalShift q range"
            )
        corrected = np.clip(
            cropped[:, 1] - baseline_asls(cropped[:, 1]), 0.0, None
        )
        corrected /= max(float(corrected.max()), np.finfo(float).tiny)
        selected = np.arange(0, len(cropped), 4)
        target = pattern_root / path.name
        np.savetxt(
            target,
            np.column_stack([cropped[selected, 0], corrected[selected]]),
            fmt=["%.5f", "%.10g"],
            header="2theta_deg baseline_corrected_normalized_intensity; CrystalShift adapter",
        )
        pattern_rows.append(
            {
                "sample_id": path.stem,
                "adapter_version": "q7_58_crop_before_asls_v1",
                "source_pattern_sha256": sha256(path),
                "source_points": len(raw),
                "source_two_theta_min_deg": raw[0, 0],
                "source_two_theta_max_deg": raw[-1, 0],
                "cropped_points_before_stride": len(cropped),
                "cropped_two_theta_min_deg": cropped[0, 0],
                "cropped_two_theta_max_deg": cropped[-1, 0],
                "stride": 4,
                "output_points": len(selected),
                "output_pattern_sha256": sha256(target),
            }
        )
    pd.DataFrame(pattern_rows).to_csv(
        output_root / "pattern_preprocessing_manifest.csv", index=False
    )

    summaries: list[dict[str, object]] = []
    all_failures: list[dict[str, object]] = []
    all_attempts: list[dict[str, object]] = []
    all_audits: list[dict[str, object]] = []
    for key in systems:
        cif_paths = sorted((cod_root / key / "cifs").glob("*.cif"))
        if not cif_paths:
            raise FileNotFoundError(
                f"No COD candidates for {key}; run prepare_cod_candidate_sets_v3.py first"
            )
        system_root = output_root / key
        system_root.mkdir(exist_ok=True)
        sticks_path = system_root / "candidate_sticks.csv"
        map_path = system_root / "phase_id_map.csv"
        failure_path = system_root / "conversion_failures.csv"
        attempt_path = system_root / "conversion_attempt_failures.csv"
        audit_path = system_root / "structure_preservation_audit.csv"
        required_resume = (sticks_path, map_path, failure_path, attempt_path, audit_path)
        if args.resume and all(path.is_file() for path in required_resume):
            existing_rows = pd.read_csv(map_path).to_dict("records")
            existing_failures = pd.read_csv(failure_path).to_dict("records")
            existing_attempts = pd.read_csv(attempt_path).to_dict("records")
            existing_audits = pd.read_csv(audit_path).to_dict("records")
            expected_names = {path.name for path in cif_paths}
            recorded_names = {
                str(row["candidate_cif_filename"])
                for row in existing_rows + existing_failures
            }
            audited_names = {
                str(row["candidate_cif_filename"]) for row in existing_audits
            }
            phase_ids = [int(row["crystalshift_phase_id"]) for row in existing_rows]
            if (
                existing_rows
                and sticks_path.stat().st_size
                and recorded_names == expected_names
                and audited_names == expected_names
                and phase_ids == list(range(len(existing_rows)))
            ):
                all_failures.extend(existing_failures)
                all_attempts.extend(existing_attempts)
                all_audits.extend(existing_audits)
                strategies = Counter(
                    str(row["conversion_strategy"])
                    for row in existing_audits
                    if row["status"] == "converted"
                )
                summaries.append(
                    {
                        "system_key": key,
                        "cod_candidate_count": len(cif_paths),
                        "converted_candidate_count": len(existing_rows),
                        "conversion_failure_count": len(existing_failures),
                        "direct_conversion_count": strategies[
                            "official_converter_direct"
                        ],
                        "symmetry_normalized_count": strategies[
                            "pymatgen_symmetry_normalized"
                        ],
                        "p1_normalized_count": strategies[
                            "pymatgen_p1_normalized"
                        ],
                    }
                )
                print(
                    f"{key}: recorded {len(existing_rows)}/{len(cif_paths)}; skipped",
                    flush=True,
                )
                continue
        blocks = []
        rows = []
        failures = []
        attempts = []
        audits = []
        candidate_manifest = pd.read_csv(
            cod_root / key / "candidate_manifest.csv", dtype=str
        )
        manifest_by_name = {
            Path(row["cif_path"]).name: row
            for row in candidate_manifest.to_dict("records")
        }
        normalized_root = system_root / "normalized_cifs"
        for path in cif_paths:
            candidate_id = database_id(path)
            audit: dict[str, object] = {
                "system_key": key,
                "candidate_cif_filename": path.name,
                "database_id": candidate_id,
                "status": "failed",
                "source_cif_sha256": sha256(path),
            }
            try:
                manifest_row = manifest_by_name.get(path.name)
                if manifest_row is None:
                    raise ValueError("candidate missing from frozen manifest")
                audit["manifest_database_id"] = manifest_row["database_id"]
                audit["database_id_match"] = (
                    candidate_id == manifest_row["database_id"]
                )
                audit["manifest_cif_sha256"] = manifest_row["cif_sha256"]
                audit["source_hash_match"] = (
                    audit["source_cif_sha256"] == manifest_row["cif_sha256"]
                )
                if not audit["database_id_match"] or not audit["source_hash_match"]:
                    raise ValueError("frozen candidate ID/hash validation failed")

                declared_symbol, declared_number = declared_space_group(path)
                structure, parse_strategy, sanitation = parse_source_structure(path)
                computed_symbol, computed_number, computed_status = analyzed_space_group(
                    structure
                )
                selected_number = declared_number or computed_number
                if selected_number is None:
                    raise ValueError("no valid declared or computed space-group number")
                selected_symbol = declared_symbol or computed_symbol
                expected_crystal_system = crystal_system_from_number(selected_number)
                element_composition = structure.composition.element_composition
                elements = sorted(str(e) for e in element_composition.elements)
                elements_subset = set(elements).issubset(set(key.split("-")))
                audit.update(
                    {
                        "source_parse_strategy": parse_strategy,
                        "sanitation_changes": json.dumps(sanitation, sort_keys=True),
                        "elements": ";".join(elements),
                        "elements_subset_of_system": elements_subset,
                        "formula": element_composition.reduced_formula,
                        "source_cell_a": structure.lattice.a,
                        "source_cell_b": structure.lattice.b,
                        "source_cell_c": structure.lattice.c,
                        "source_cell_alpha": structure.lattice.alpha,
                        "source_cell_beta": structure.lattice.beta,
                        "source_cell_gamma": structure.lattice.gamma,
                        "source_site_count": len(structure),
                        "source_occupancy_sum": sum(
                            float(amount)
                            for site in structure
                            for amount in site.species.values()
                        ),
                        "source_occupancy_signature": occupancy_signature(structure),
                        "declared_space_group_symbol": declared_symbol,
                        "declared_space_group_number": declared_number or "",
                        "computed_space_group_symbol": computed_symbol,
                        "computed_space_group_number": computed_number or "",
                        "computed_space_group_status": computed_status,
                        "declared_computed_sg_match": (
                            declared_number == computed_number
                            if declared_number is not None
                            and computed_number is not None
                            else "not_comparable"
                        ),
                        "selected_space_group_symbol": selected_symbol,
                        "selected_space_group_number": selected_number,
                        "selected_crystal_system": expected_crystal_system,
                    }
                )

                try:
                    (
                        block,
                        strategy,
                        normalized_path,
                        validation,
                        candidate_attempts,
                        converter_system,
                    ) = convert_with_fallback(
                        converter,
                        path,
                        structure,
                        expected_crystal_system,
                        normalized_root,
                    )
                except AllConversionsFailed as error:
                    for item in error.attempts:
                        attempts.append(
                            {
                                "system_key": key,
                                "candidate_cif_filename": path.name,
                                "database_id": candidate_id,
                                **item,
                            }
                        )
                    raise
                for item in candidate_attempts:
                    attempts.append(
                        {
                            "system_key": key,
                            "candidate_cif_filename": path.name,
                            "database_id": candidate_id,
                            **item,
                        }
                    )

                phase_id = len(rows)
                first, rest = block.split(",", maxsplit=1)
                if first.strip() != "0":
                    raise ValueError(f"Unexpected converter phase id: {first!r}")
                blocks.append(f"{phase_id},{rest}")
                rows.append(
                    {
                        "crystalshift_phase_id": phase_id,
                        "candidate_cif_filename": path.name,
                        "database_id": candidate_id,
                        "formula": element_composition.reduced_formula,
                        "space_group_symbol": selected_symbol,
                        "space_group_number": selected_number,
                        "elements": ";".join(elements),
                        "conversion_strategy": strategy,
                        "normalized_cif_path": normalized_path,
                    }
                )
                after = structure
                normalized_sha = ""
                if normalized_path:
                    normalized_file = ROOT / normalized_path
                    normalized_sha = sha256(normalized_file)
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        after = CifParser(
                            normalized_file, check_cif=False
                        ).parse_structures(
                            primitive=False, check_occu=False, on_error="raise"
                        )[0]
                after_symbol, after_number, after_status = analyzed_space_group(after)
                audit.update(
                    {
                        "status": "converted",
                        "converter_reported_crystal_system": converter_system,
                        "converter_crystal_system_corrected": (
                            converter_system != expected_crystal_system
                        ),
                        "conversion_strategy": strategy,
                        "normalized_cif_path": normalized_path,
                        "normalized_cif_sha256": normalized_sha,
                        "normalized_space_group_symbol": after_symbol,
                        "normalized_space_group_number": after_number or "",
                        "normalized_space_group_status": after_status,
                        "normalized_site_count": len(after),
                        "normalized_occupancy_signature": occupancy_signature(after),
                        **validation,
                        "substantive_change": not bool(
                            validation["validation_passed"]
                        ),
                    }
                )
            except Exception as error:
                failures.append(
                    {
                        "system_key": key,
                        "candidate_cif_filename": path.name,
                        "database_id": candidate_id,
                        "error_type": type(error).__name__,
                        "error": str(error),
                    }
                )
                audit["error_type"] = type(error).__name__
                audit["error"] = str(error)
            audits.append(audit)
        all_failures.extend(failures)
        all_attempts.extend(attempts)
        all_audits.extend(audits)
        if not rows:
            raise RuntimeError(f"No COD candidate could be converted for {key}")
        sticks_path.write_text("".join(blocks), encoding="utf-8")
        pd.DataFrame(rows).to_csv(map_path, index=False)
        pd.DataFrame(
            failures,
            columns=[
                "system_key",
                "candidate_cif_filename",
                "database_id",
                "error_type",
                "error",
            ],
        ).to_csv(failure_path, index=False)
        pd.DataFrame(
            attempts,
            columns=[
                "system_key",
                "candidate_cif_filename",
                "database_id",
                "stage",
                "error_type",
                "error",
            ],
        ).to_csv(attempt_path, index=False)
        pd.DataFrame(audits).to_csv(audit_path, index=False)
        strategies = Counter(row["conversion_strategy"] for row in rows)
        summaries.append(
            {
                "system_key": key,
                "cod_candidate_count": len(cif_paths),
                "converted_candidate_count": len(rows),
                "conversion_failure_count": len(failures),
                "direct_conversion_count": strategies[
                    "official_converter_direct"
                ],
                "symmetry_normalized_count": strategies[
                    "pymatgen_symmetry_normalized"
                ],
                "p1_normalized_count": strategies["pymatgen_p1_normalized"],
            }
        )
        print(
            f"{key}: {len(rows)}/{len(cif_paths)} CrystalShift candidates converted",
            flush=True,
        )
    pd.DataFrame(
        summaries,
        columns=[
            "system_key",
            "cod_candidate_count",
            "converted_candidate_count",
            "conversion_failure_count",
            "direct_conversion_count",
            "symmetry_normalized_count",
            "p1_normalized_count",
        ],
    ).to_csv(output_root / "preparation_summary.csv", index=False)
    pd.DataFrame(
        all_failures,
        columns=[
            "system_key",
            "candidate_cif_filename",
            "database_id",
            "error_type",
            "error",
        ],
    ).to_csv(output_root / "conversion_failures.csv", index=False)
    pd.DataFrame(
        all_attempts,
        columns=[
            "system_key",
            "candidate_cif_filename",
            "database_id",
            "stage",
            "error_type",
            "error",
        ],
    ).to_csv(output_root / "conversion_attempt_failures.csv", index=False)
    pd.DataFrame(all_audits).to_csv(
        output_root / "structure_preservation_audit.csv", index=False
    )
    converted_audits = [row for row in all_audits if row["status"] == "converted"]
    strategy_counts = Counter(
        str(row["conversion_strategy"]) for row in converted_audits
    )
    summary = {
        "candidate_records": len(all_audits),
        "converted_records": len(converted_audits),
        "failed_records": len(all_failures),
        "conversion_strategy_counts": strategy_counts,
        "attempt_failure_count": len(all_attempts),
        "attempt_failure_types": Counter(
            str(row["error_type"]) for row in all_attempts
        ),
        "final_failure_types": Counter(
            str(row["error_type"]) for row in all_failures
        ),
        "pymatgen_parseable_but_final_conversion_failed": sum(
            row.get("source_parse_strategy") in {
                "direct_pymatgen_parse",
                "structured_placeholder_cleanup",
            }
            for row in all_audits
            if row["status"] == "failed"
        ),
        "structured_placeholder_cleanup_count": sum(
            row.get("source_parse_strategy") == "structured_placeholder_cleanup"
            for row in converted_audits
        ),
        "structure_validation_failure_count": sum(
            not bool(row.get("validation_passed", False)) for row in converted_audits
        ),
        "substantive_change_count": sum(
            bool(row.get("substantive_change", False)) for row in converted_audits
        ),
        "declared_computed_space_group_mismatch_count": sum(
            row.get("declared_computed_sg_match") is False for row in converted_audits
        ),
        "converter_crystal_system_correction_count": sum(
            bool(row.get("converter_crystal_system_corrected", False))
            for row in converted_audits
        ),
        "candidate_element_system_mismatch_count": sum(
            not bool(row.get("elements_subset_of_system", False))
            for row in converted_audits
        ),
        "private_truth_used": False,
    }
    (output_root / "normalization_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    rules = {
        "version": "crystalshift_cod_v3_v2",
        "selection_dependence": "none; identical rules for every frozen candidate",
        "converter_order": [
            "official converter on frozen CIF",
            "pymatgen symmetry-normalized CIF after strict round-trip validation",
            "pymatgen P1 explicit-site CIF after strict round-trip validation",
        ],
        "source_parse_fallback": (
            "structured removal of atom-loop rows without species/coordinates and "
            "invalid attached-hydrogen metadata only"
        ),
        "normalized_cif_serialization": (
            "pymatgen CifWriter at 8 significant figures with max_len=2048 so each "
            "atom-site loop record remains on one line for xrayutilities"
        ),
        "round_trip_requirements": {
            "elements": "exact",
            "composition": "rtol=1e-6, atol=1e-6",
            "cell_max_abs_delta": 1e-5,
            "site_count": "exact",
            "per_site_occupancy_signature": "exact after 8-decimal rounding",
            "structure_matcher": "must pass without scaling or supercells",
        },
        "space_group_rule": (
            "use valid source-declared IT number; otherwise computed number at "
            "symprec=0.1 angstrom and angle_tolerance=5 degrees"
        ),
        "candidate_element_mismatch_rule": (
            "retain every frozen candidate without changing its CIF; record when "
            "parsed CIF elements are not a subset of the front-end system key"
        ),
        "q_range_nm_inverse": [7.0, 58.0],
        "wavelength_angstrom": 1.5406,
        "pattern_range_rule": (
            "crop every experimental pattern to q=7.0..58.0 nm^-1 before "
            "baseline subtraction, normalization, and stride-4 downsampling"
        ),
        "pattern_adapter_version": "q7_58_crop_before_asls_v1",
        "private_truth_used": False,
    }
    (output_root / "normalization_rules.json").write_text(
        json.dumps(rules, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    snapshot_root.mkdir(parents=True, exist_ok=True)
    for name in (
        "preparation_summary.csv",
        "conversion_failures.csv",
        "conversion_attempt_failures.csv",
        "structure_preservation_audit.csv",
        "normalization_summary.json",
        "normalization_rules.json",
        "pattern_preprocessing_manifest.csv",
    ):
        shutil.copy2(output_root / name, snapshot_root / name)


if __name__ == "__main__":
    main()
