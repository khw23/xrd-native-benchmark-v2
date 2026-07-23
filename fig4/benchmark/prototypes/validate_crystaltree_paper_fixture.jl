using JSON
using LinearAlgebra
using SHA
using CrystalShift
using CrystalShift: CrystalPhase, Gauss, LM, OptimizationSettings, Simple
using CrystalTree
using CrystalTree: Lazytree, LeastSquares, TreeSearchSettings
using CrystalTree: get_phase_number, get_probabilities, search!

const PAPER_PRIORS = (
    std_noise = 1e-2,
    mean_theta = [1.0, 0.5, 0.5],
    std_theta = [0.1, 0.05, 0.1],
)
const ITERATIONS = [128, 512]
const EXPECTED_SELECTION = [1, 11, 21, 22, 2, 3, 4, 5, 31, 33, 34, 35]
const WARMUP_ROW = 6

function read_npy_fortran_float64(path)
    open(path, "r") do io
        read(io, 6) == UInt8[0x93, 0x4e, 0x55, 0x4d, 0x50, 0x59] ||
            error("Not a NumPy file: $(path)")
        major = read(io, UInt8)
        minor = read(io, UInt8)
        header_length = if major == 1
            Int(ltoh(read(io, UInt16)))
        elseif major in (2, 3)
            Int(ltoh(read(io, UInt32)))
        else
            error("Unsupported NPY version $(major).$(minor)")
        end
        header = String(read(io, header_length))
        occursin("'descr': '<f8'", header) || error("Expected little-endian Float64 NPY")
        occursin("'fortran_order': True", header) || error("Expected Fortran-order NPY")
        shape_match = match(r"'shape': \((\d+),\s*(\d+)\)", header)
        isnothing(shape_match) && error("Could not parse NPY matrix shape")
        rows, columns = parse.(Int, shape_match.captures)
        values = Vector{Float64}(undef, rows * columns)
        read!(io, values)
        eof(io) || error("Unexpected trailing bytes in NPY file")
        return reshape(values, rows, columns)
    end
end

function read_solutions(path)
    rows = Vector{NamedTuple}()
    for (row_index, line) in enumerate(eachline(path))
        fields = split(line, ',')
        length(fields) == 7 || error("Invalid solution row $(row_index)")
        sample_index = parse(Int, fields[1])
        activation = parse.(Float64, fields[2:end])
        truth = Int.(activation .> 0)
        push!(rows, (; row_index, sample_index, activation, truth,
                     phase_count=sum(truth)))
    end
    return rows
end

function select_fixture_rows(solutions)
    # Pre-registered rule: concatenate the first four source-order rows with
    # exactly 1, 2, and 3 nonzero ground-truth activations, in that order.
    selected = Int[]
    for phase_count in 1:3
        matches = [row.row_index for row in solutions if row.phase_count == phase_count]
        length(matches) >= 4 || error("Fewer than four $(phase_count)-phase rows")
        append!(selected, matches[1:4])
    end
    selected == EXPECTED_SELECTION || error(
        "Public fixture changed: selected $(selected), expected $(EXPECTED_SELECTION)"
    )
    return selected
end

function prediction_counts(node)
    counts = zeros(Int, 7)
    for phase in node.phase_model.CPs
        counts[get_phase_number(phase.name)] += 1
    end
    return counts
end

function run_setting(phases, x, patterns, solutions, selected, maxiter)
    opt_settings = OptimizationSettings{Float64}(
        PAPER_PRIORS.std_noise,
        PAPER_PRIORS.mean_theta,
        PAPER_PRIORS.std_theta,
        maxiter,
        true,
        LM,
        "LS",
        Simple,
        1,
    )
    tree_settings = TreeSearchSettings{Float64}(3, 3, false, false, 5.0, opt_settings)
    sample_results = Any[]
    total_tp = 0
    total_fp = 0
    total_fn = 0
    correct = 0
    failures = 0
    setting_started = time()

    for row_index in selected
        row = solutions[row_index]
        started = time()
        try
            y = copy(patterns[row_index, :])
            maximum(y) > 0 || error("Non-positive fixture spectrum")
            y ./= maximum(y)
            levels = search!(Lazytree(phases, x), x, y, tree_settings)
            nodes = reduce(vcat, levels[2:end])
            isempty(nodes) && error("Tree search returned no non-root hypotheses")
            probabilities = get_probabilities(
                nodes,
                x,
                y,
                PAPER_PRIORS.std_noise,
                PAPER_PRIORS.mean_theta,
                PAPER_PRIORS.std_theta;
                objective=LeastSquares(),
                renormalize=true,
                normalization_constant=1.0,
            )
            best_index = argmax(probabilities)
            best = nodes[best_index]
            predicted = prediction_counts(best)
            truth = vcat(row.truth, 0)
            tp = sum(min.(predicted, truth))
            fp = sum(predicted) - tp
            fn = sum(truth) - tp
            exact = predicted == truth
            total_tp += tp
            total_fp += fp
            total_fn += fn
            correct += exact
            push!(sample_results, Dict(
                "row_index" => row.row_index,
                "sample_index" => row.sample_index,
                "ground_truth_phase_count" => row.phase_count,
                "ground_truth_phase_vector" => truth,
                "predicted_phase_vector" => predicted,
                "predicted_phase_names" => [phase.name for phase in best.phase_model.CPs],
                "full_combination_top1_correct" => exact,
                "top1_probability" => probabilities[best_index],
                "residual_norm" => norm(best.residual),
                "runtime_seconds" => time() - started,
                "status" => "ok",
            ))
        catch err
            failures += 1
            push!(sample_results, Dict(
                "row_index" => row.row_index,
                "sample_index" => row.sample_index,
                "ground_truth_phase_count" => row.phase_count,
                "runtime_seconds" => time() - started,
                "status" => "error",
                "error_type" => string(typeof(err)),
                "error_message" => sprint(showerror, err),
            ))
        end
    end

    successful = length(selected) - failures
    return Dict(
        "maxiter" => maxiter,
        "sample_count" => length(selected),
        "successful_count" => successful,
        "failure_count" => failures,
        "full_combination_top1_correct" => correct,
        "full_combination_top1_accuracy" => successful == 0 ? nothing : correct / successful,
        "phase_precision_micro" => total_tp + total_fp == 0 ? nothing : total_tp / (total_tp + total_fp),
        "phase_recall_micro" => total_tp + total_fn == 0 ? nothing : total_tp / (total_tp + total_fn),
        "residual_norm_mean" => successful == 0 ? nothing : sum(
            result["residual_norm"] for result in sample_results if result["status"] == "ok"
        ) / successful,
        "runtime_seconds" => time() - setting_started,
        "samples" => sample_results,
    )
end

function write_markdown(path, result)
    runs = Dict(run["maxiter"] => run for run in result["runs"])
    open(path, "w") do io
        println(io, "# CrystalTree public Al-Fe-Li-O parameter audit\n")
        println(io, "Status: **$(result["status"])**\n")
        println(io, "This audit uses only the upstream public paper fixture. No private benchmark truth was read.\n")
        println(io, "## Fixed selection\n")
        println(io, "Before execution, the rule was fixed as the first four source-order rows having exactly 1, 2, and 3 nonzero activations, concatenated by phase count. Selected rows: `$(join(result["selected_row_indices"], ", "))`.\n")
        println(io, "Public row $(result["warmup"]["row_index"]) was run once at 128 iterations before timing and was excluded from every metric. This removes first-call JIT compilation from the comparison.\n")
        println(io, "## Published configuration\n")
        println(io, "`LM`, `Simple` (not EM), least squares, `std_noise=0.01`, `mean_theta=[1.0, 0.5, 0.5]`, `std_theta=[0.1, 0.05, 0.1]`, one inactive EM loop, regularization on, no amorphous phase, and background off. The paper script adds unseeded random positive noise; this audit omits that augmentation so both iteration settings receive byte-identical public spectra.\n")
        println(io, "## Results\n")
        println(io, "| maxiter | success | failures | strict top-1 | phase precision | phase recall | mean residual | runtime (s) |")
        println(io, "|---:|---:|---:|---:|---:|---:|---:|---:|")
        for maxiter in ITERATIONS
            run = runs[maxiter]
            println(io, "| $(maxiter) | $(run["successful_count"])/$(run["sample_count"]) | $(run["failure_count"]) | $(round(run["full_combination_top1_accuracy"], digits=4)) | $(round(run["phase_precision_micro"], digits=4)) | $(round(run["phase_recall_micro"], digits=4)) | $(round(run["residual_norm_mean"], digits=6)) | $(round(run["runtime_seconds"], digits=1)) |")
        end
        println(io, "\n## Gate\n")
        println(io, "The pre-registered gate requires zero failures in both settings and strict full-combination top-1 accuracy at 512 iterations to be no lower than at 128. Precision, recall, residual, and runtime are reported but do not alter the gate.\n")
        println(io, "This is a small public sensitivity audit, not validation of the private benchmark or of the README-derived production priors.")
    end
end

function main()
    length(ARGS) == 2 || error(
        "usage: validate_crystaltree_paper_fixture.jl OUTPUT_JSON OUTPUT_MARKDOWN"
    )
    root = normpath(joinpath(@__DIR__, "..", "..", ".."))
    fixture_root = joinpath(root, "fig4", "benchmark", "third_party", "CrystalShift.jl", "paper", "data", "AlFeLiO")
    paper_script = joinpath(dirname(dirname(fixture_root)), "AlFeLiO.jl")
    sticks_path = joinpath(fixture_root, "sticks.csv")
    patterns_path = joinpath(fixture_root, "alfeli.npy")
    solutions_path = joinpath(fixture_root, "sol.csv")
    all(isfile, (paper_script, sticks_path, patterns_path, solutions_path)) ||
        error("Upstream Al-Fe-Li-O paper fixture is incomplete")

    phases = open(sticks_path, "r") do io
        CrystalPhase(io, 0.1, Gauss())
    end
    patterns = read_npy_fortran_float64(patterns_path)
    solutions = read_solutions(solutions_path)
    size(patterns, 1) == length(solutions) || error("Pattern/solution row mismatch")
    size(patterns, 2) == 650 || error("Unexpected fixture spectrum length")
    selected = select_fixture_rows(solutions)
    x = collect(15.0:0.1:79.9)
    warmup_run = run_setting(
        phases, x, patterns, solutions, [WARMUP_ROW], first(ITERATIONS)
    )
    warmup_run["failure_count"] == 0 || error("Public fixture warm-up failed")
    runs = [run_setting(phases, x, patterns, solutions, selected, maxiter)
            for maxiter in ITERATIONS]
    runs_by_iter = Dict(run["maxiter"] => run for run in runs)
    gate_passed = all(run["failure_count"] == 0 for run in runs) &&
        runs_by_iter[512]["full_combination_top1_accuracy"] >=
        runs_by_iter[128]["full_combination_top1_accuracy"]

    result = Dict(
        "status" => gate_passed ? "passed" : "failed",
        "gate_scope" => "public paper-fixture maxiter sensitivity only",
        "private_truth_used" => false,
        "selection_rule" => "first four source-order rows with exactly 1, then 2, then 3 nonzero activations",
        "selection_frozen_before_execution" => true,
        "selected_row_indices" => selected,
        "selected_sample_indices" => [solutions[index].sample_index for index in selected],
        "warmup" => Dict(
            "row_index" => WARMUP_ROW,
            "maxiter" => first(ITERATIONS),
            "excluded_from_metrics" => true,
            "runtime_seconds" => warmup_run["runtime_seconds"],
        ),
        "candidate_count" => length(phases),
        "fixture_sha256" => Dict(
            "paper_script" => bytes2hex(open(sha256, paper_script)),
            "sticks_csv" => bytes2hex(open(sha256, sticks_path)),
            "patterns_npy" => bytes2hex(open(sha256, patterns_path)),
            "solutions_csv" => bytes2hex(open(sha256, solutions_path)),
        ),
        "published_configuration" => Dict(
            "optimization_method" => "LM",
            "optimization_mode" => "Simple",
            "em_used" => false,
            "em_loop_num" => 1,
            "objective" => "LeastSquares",
            "std_noise" => PAPER_PRIORS.std_noise,
            "mean_theta" => PAPER_PRIORS.mean_theta,
            "std_theta" => PAPER_PRIORS.std_theta,
            "peak_profile" => "Gauss",
            "initial_peak_width" => 0.1,
            "regularization" => true,
            "amorphous" => false,
            "background" => false,
            "background_length_inactive" => 5.0,
            "tree_depth" => 3,
            "candidate_expansion_count" => 3,
        ),
        "spectrum_handling" => "raw public fixture row normalized by its maximum; paper script's unseeded random noise augmentation omitted to keep spectra identical",
        "gate_rule" => "both settings have zero failures and 512 strict top-1 accuracy is not lower than 128",
        "runs" => runs,
    )
    mkpath(dirname(abspath(ARGS[1])))
    open(ARGS[1], "w") do io
        JSON.print(io, result, 2)
        println(io)
    end
    write_markdown(ARGS[2], result)
    println(JSON.json(Dict(
        "status" => result["status"],
        "selected_rows" => selected,
        "runs" => [Dict(
            "maxiter" => run["maxiter"],
            "top1" => run["full_combination_top1_accuracy"],
            "precision" => run["phase_precision_micro"],
            "recall" => run["phase_recall_micro"],
            "failures" => run["failure_count"],
            "runtime_seconds" => run["runtime_seconds"],
        ) for run in runs],
    )))
    gate_passed || error("Public paper-fixture parameter gate failed")
end

main()
