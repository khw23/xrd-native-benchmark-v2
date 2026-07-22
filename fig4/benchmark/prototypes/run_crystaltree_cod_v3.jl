using DelimitedFiles
using JSON
using LinearAlgebra
using SHA
using CrystalShift
using CrystalShift: CrystalPhase, FixedPseudoVoigt, OptimizationSettings
using CrystalTree
using CrystalTree: Lazytree, TreeSearchSettings, get_phase_ids, get_probabilities, search!

const ROOT = normpath(joinpath(@__DIR__, "..", "..", ".."))
const BLIND_ROOT = joinpath(ROOT, "fig4", "benchmark", "datasets", "atomly_core_v3", "native_blind_package_v3")
const INPUT_ROOT = joinpath(ROOT, "fig4", "benchmark", "method_inputs", "crystalshift_cod_v3")
const COD_ROOT = joinpath(ROOT, "fig4", "benchmark", "method_inputs", "cod_native_v3")
const RESULT_ROOT = joinpath(ROOT, "fig4", "benchmark", "results", "atomly_core_v3", "crystaltree_cod_frontend")
const WAVELENGTH_ANGSTROM = 1.5406
const DEFAULT_MAXITER = 512

function parse_args()
    limit = nothing
    sample_ids = String[]
    dataset_families = String[]
    resume = false
    rerun_selected = false
    maxiter = DEFAULT_MAXITER
    blind_root = BLIND_ROOT
    input_root = INPUT_ROOT
    cod_root = COD_ROOT
    result_root = RESULT_ROOT
    i = 1
    while i <= length(ARGS)
        if ARGS[i] == "--limit"
            limit = parse(Int, ARGS[i + 1]); i += 2
        elseif ARGS[i] == "--sample-id"
            push!(sample_ids, ARGS[i + 1]); i += 2
        elseif ARGS[i] == "--dataset-family"
            push!(dataset_families, ARGS[i + 1]); i += 2
        elseif ARGS[i] == "--resume"
            resume = true; i += 1
        elseif ARGS[i] == "--rerun-selected"
            rerun_selected = true; i += 1
        elseif ARGS[i] == "--maxiter"
            maxiter = parse(Int, ARGS[i + 1]); i += 2
        elseif ARGS[i] == "--blind-root"
            blind_root = abspath(ARGS[i + 1]); i += 2
        elseif ARGS[i] == "--input-root"
            input_root = abspath(ARGS[i + 1]); i += 2
        elseif ARGS[i] == "--cod-root"
            cod_root = abspath(ARGS[i + 1]); i += 2
        elseif ARGS[i] == "--result-root"
            result_root = abspath(ARGS[i + 1]); i += 2
        else
            error("Unknown argument: $(ARGS[i])")
        end
    end
    maxiter > 0 || error("--maxiter must be positive")
    rerun_selected && !resume && error("--rerun-selected requires --resume")
    rerun_selected && isempty(sample_ids) && error("--rerun-selected requires explicit --sample-id values")
    return limit, sample_ids, dataset_families, resume, rerun_selected, maxiter, blind_root, input_root, cod_root, result_root
end

function read_simple_csv(path)
    data, header = readdlm(path, ',', Any, '\n'; header=true)
    names = String.(vec(header))
    if isempty(data)
        return Any[]
    end
    if ndims(data) == 1
        data = reshape(data, 1, :)
    end
    return [Dict(names[j] => data[i, j] for j in eachindex(names)) for i in axes(data, 1)]
end

function csv_escape(value)
    value === missing && return ""
    text = string(value)
    if occursin(',', text) || occursin('"', text) || occursin('\n', text)
        return "\"" * replace(text, "\"" => "\"\"") * "\""
    end
    return text
end

function write_records_csv(path, columns, records)
    open(path, "w") do io
        println(io, join(columns, ','))
        for record in records
            println(io, join((csv_escape(get(record, column, "")) for column in columns), ','))
        end
    end
end

function write_json(path, value)
    open(path, "w") do io
        JSON.print(io, value, 2); println(io)
    end
end

system_key(elements) = join(sort(split(String(elements), ';')), "-")

function load_phases(sticks_path)
    blocks = split(read(sticks_path, String), "#\n")
    filter!(!isempty, blocks)
    return CrystalPhase.(String.(blocks), (0.10,), (FixedPseudoVoigt(0.5),))
end

function main()
    limit, requested, requested_families, resume, rerun_selected, maxiter, blind_root, input_root, cod_root, result_root = parse_args()
    manifest_path = joinpath(blind_root, "sample_manifest.csv")
    samples = read_simple_csv(manifest_path)
    !isempty(requested_families) && (samples = filter(row -> String(row["dataset_family"]) in requested_families, samples))
    !isempty(requested) && (samples = filter(row -> String(row["sample_id"]) in requested, samples))
    !isnothing(limit) && (samples = first(samples, min(limit, length(samples))))
    isempty(samples) && error("No samples selected")

    mkpath(result_root)
    prediction_path = joinpath(result_root, "predictions.csv")
    hypothesis_path = joinpath(result_root, "top_hypotheses.csv")
    record_path = joinpath(result_root, "run_records.json")
    environment_path = joinpath(result_root, "environment.json")
    if !resume && any(isfile, (prediction_path, hypothesis_path, record_path, environment_path))
        error("Result files already exist in $(result_root). Use --resume or a new --result-root; existing results will not be overwritten.")
    end
    environment = Dict(
        "method" => "CrystalShift + CrystalTree with COD front-end",
        "julia_version" => string(VERSION),
        "machine" => Sys.MACHINE,
        "julia_threads" => Threads.nthreads(),
        "blind_manifest" => manifest_path,
        "blind_manifest_sha256" => bytes2hex(sha256(read(manifest_path))),
        "input_root" => input_root,
        "cod_root" => cod_root,
        "result_root" => result_root,
        "wavelength_angstrom" => WAVELENGTH_ANGSTROM,
        "tree_depth" => 3,
        "candidate_expansion_count" => 3,
        "max_phases" => 3,
        "private_truth_used" => false,
    )
    if resume && isfile(environment_path)
        previous_environment = JSON.parsefile(environment_path)
        for key in ("blind_manifest_sha256", "input_root", "cod_root")
            get(previous_environment, key, nothing) == environment[key] ||
                error("Existing environment differs for $(key); choose a new --result-root")
        end
    end
    predictions = resume && isfile(prediction_path) ? read_simple_csv(prediction_path) : Any[]
    hypotheses = resume && isfile(hypothesis_path) ? read_simple_csv(hypothesis_path) : Any[]
    records = resume && isfile(record_path) ? JSON.parsefile(record_path) : Any[]
    completed = Set(String(row["sample_id"]) for row in records if get(row, "status", "") == "ok")

    latest_ok = Dict{String, Any}()
    for row in records
        get(row, "status", "") == "ok" || continue
        latest_ok[String(row["sample_id"])] = row
    end
    mismatched = Set(
        sample_id for (sample_id, row) in latest_ok
        if get(row, "maxiter", nothing) != maxiter
    )
    allowed_mismatches = rerun_selected ? Set(requested) : Set{String}()
    if !issubset(mismatched, allowed_mismatches)
        error(
            "Existing successful samples use a different maxiter: " *
            join(sort(collect(setdiff(mismatched, allowed_mismatches))), ", ") *
            ". Rerun them explicitly with --resume --rerun-selected --sample-id ..."
        )
    end
    write_json(environment_path, environment)

    std_noise = 0.1
    mean_theta = [1.0, 0.5, 0.2]
    std_theta = [0.05, 2.0, 1.0]
    opt_settings = OptimizationSettings{Float64}(std_noise, mean_theta, std_theta, maxiter)
    tree_settings = TreeSearchSettings{Float64}(3, 3, false, false, 5.0, opt_settings)

    prediction_columns = ["sample_id", "method", "solution_rank", "phase_rank",
                          "predicted_formula", "predicted_space_group_symbol",
                          "predicted_space_group_number", "predicted_database",
                          "predicted_database_id", "predicted_weight_fraction",
                          "confidence_or_score", "runtime_seconds", "status_or_note",
                          "predicted_cif_path"]
    hypothesis_columns = ["sample_id", "hypothesis_rank", "predicted_database_ids",
                          "model_probability", "n_phases", "residual_norm"]

    for sample in samples
        sample_id = String(sample["sample_id"])
        if sample_id in completed && !(rerun_selected && sample_id in requested)
            println("$(sample_id): already complete; skipped"); continue
        end
        filter!(row -> String(row["sample_id"]) != sample_id, predictions)
        filter!(row -> String(row["sample_id"]) != sample_id, hypotheses)
        attempt = count(row -> String(row["sample_id"]) == sample_id, records) + 1
        started = time()
        try
            key = system_key(sample["sample_elements"])
            system_root = joinpath(input_root, key)
            mapping = read_simple_csv(joinpath(system_root, "phase_id_map.csv"))
            isempty(mapping) && error("No CrystalShift candidates for $(key)")
            phases = load_phases(joinpath(system_root, "candidate_sticks.csv"))
            length(phases) == length(mapping) || error("Candidate/map length mismatch for $(key)")
            id_to_row = Dict(Int(row["crystalshift_phase_id"]) => row for row in mapping)

            xy = readdlm(joinpath(input_root, "patterns_preprocessed", String(sample["pattern_filename"]));
                         comments=true, comment_char='#')
            two_theta = Float64.(xy[:, 1])
            y = Float64.(xy[:, 2]); y ./= maximum(y)
            q_nm_inv = 10 .* (4pi .* sin.(deg2rad.(two_theta ./ 2)) ./ WAVELENGTH_ANGSTROM)

            levels = search!(Lazytree(phases, q_nm_inv), q_nm_inv, y, tree_settings)
            nodes = reduce(vcat, levels[2:end])
            probabilities = get_probabilities(nodes, q_nm_inv, y, std_noise,
                                              mean_theta, std_theta;
                                              renormalize=true, normalization_constant=1.0)
            ranking = sortperm(probabilities; rev=true)
            elapsed = time() - started
            for (h_rank, node_index) in enumerate(ranking[1:min(3, length(ranking))])
                node = nodes[node_index]
                ids = get_phase_ids(node)
                push!(hypotheses, Dict(
                    "sample_id" => sample_id,
                    "hypothesis_rank" => h_rank,
                    "predicted_database_ids" => join([string(id_to_row[id]["database_id"]) for id in ids], ";"),
                    "model_probability" => probabilities[node_index],
                    "n_phases" => length(ids),
                    "residual_norm" => norm(node.residual),
                ))
            end

            best_index = ranking[1]
            best = nodes[best_index]
            best_ids = get_phase_ids(best)
            activations = CrystalShift.get_fraction(best.phase_model.CPs)
            phase_order = sortperm(activations; rev=true)
            selected_root = joinpath(result_root, "selected_cifs", sample_id)
            if rerun_selected && isdir(selected_root)
                rm(selected_root; recursive=true)
            end
            mkpath(selected_root)
            for (phase_rank, position) in enumerate(phase_order)
                phase_id = best_ids[position]
                row = id_to_row[phase_id]
                filename = String(row["candidate_cif_filename"])
                database_id = string(row["database_id"])
                source_cif = joinpath(cod_root, key, "cifs", filename)
                isfile(source_cif) || error("Selected CIF does not exist: $(source_cif)")
                selected_cif = joinpath(
                    selected_root,
                    "solution1_phase$(phase_rank)_COD_$(database_id).cif",
                )
                cp(source_cif, selected_cif; force=true)
                push!(predictions, Dict(
                    "sample_id" => sample_id,
                    "method" => "CrystalShift + CrystalTree with COD front-end",
                    "solution_rank" => 1,
                    "phase_rank" => phase_rank,
                    "predicted_formula" => row["formula"],
                    "predicted_space_group_symbol" => row["space_group_symbol"],
                    "predicted_space_group_number" => row["space_group_number"],
                    "predicted_database" => "COD",
                    "predicted_database_id" => database_id,
                    "predicted_weight_fraction" => missing,
                    "confidence_or_score" => probabilities[best_index],
                    "runtime_seconds" => elapsed,
                    "status_or_note" => "identification_ok; activation=$(activations[position]) is not physical QPA; model_probability_is_uncalibrated",
                    "predicted_cif_path" => relpath(selected_cif, ROOT),
                ))
            end
            push!(records, Dict(
                "sample_id" => sample_id,
                "attempt" => attempt,
                "status" => "ok",
                "runtime_seconds" => elapsed,
                "candidate_frontend" => "Dara COD filtered index 2024",
                "candidate_count" => length(phases),
                "tree_depth" => 3,
                "candidate_expansion_count" => 3,
                "max_phases" => 3,
                "std_noise" => std_noise,
                "mean_theta" => mean_theta,
                "std_theta" => std_theta,
                "maxiter" => maxiter,
                "configuration_id" => "simple_fixed_sigma_0p1_maxiter$(maxiter)",
                "julia_threads" => Threads.nthreads(),
                "phase_count_prior" => "global upper bound only; per-sample truth hidden",
                "predicted_phase_count" => length(best_ids),
                "model_probability" => probabilities[best_index],
                "model_probability_calibrated" => false,
                "fraction_type" => "activation_not_validated_as_weight_or_mole_fraction",
            ))
            println("$(sample_id): $(length(phases)) candidates -> $(length(best_ids)) phases, $(round(elapsed, digits=1)) s")
        catch err
            elapsed = time() - started
            push!(records, Dict("sample_id" => sample_id, "attempt" => attempt,
                                "status" => "error",
                                "runtime_seconds" => elapsed,
                                "error_type" => string(typeof(err)),
                                "error_message" => sprint(showerror, err),
                                "error" => sprint(showerror, err, catch_backtrace())))
            println("$(sample_id): ERROR after $(round(elapsed, digits=1)) s: $(sprint(showerror, err))")
        end
        write_records_csv(prediction_path, prediction_columns, predictions)
        write_records_csv(hypothesis_path, hypothesis_columns, hypotheses)
        write_json(record_path, records)
    end
end

main()
