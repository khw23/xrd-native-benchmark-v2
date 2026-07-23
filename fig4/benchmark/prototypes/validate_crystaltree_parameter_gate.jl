using JSON
using LinearAlgebra
using SHA
using CrystalShift
using CrystalShift: CrystalPhase, FixedPseudoVoigt, OptimizationSettings
using CrystalTree
using CrystalTree: Lazytree, TreeSearchSettings, get_phase_ids, search!

function load_phases(path)
    blocks = split(read(path, String), "#\n")
    filter!(!isempty, blocks)
    CrystalPhase.(String.(blocks), (0.10,), (FixedPseudoVoigt(0.5),))
end

function main()
    length(ARGS) == 1 || error("usage: validate_crystaltree_parameter_gate.jl OUTPUT_JSON")
    package_root = dirname(dirname(pathof(CrystalTree)))
    fixture = joinpath(package_root, "data", "sticks.csv")
    isfile(fixture) || error("Official CrystalTree fixture is missing: $(fixture)")

    phases = load_phases(fixture)
    x = collect(LinRange(8.0, 45.0, 512))
    y = phases[1].(x) + phases[2].(x)
    y ./= maximum(y)

    std_noise = 0.1
    mean_theta = [1.0, 0.5, 0.2]
    std_theta = [0.05, 2.0, 1.0]
    # The paper's Al-Fe-Li-O reproduction script uses 512 iterations for the
    # multiphase search. The package constructor default (128) is only a
    # software default and is not the benchmark setting.
    maxiter = 512
    depth = 3
    expansion_count = 3
    settings = TreeSearchSettings{Float64}(
        depth,
        expansion_count,
        false,
        false,
        5.0,
        OptimizationSettings{Float64}(
            std_noise, mean_theta, std_theta, maxiter
        ),
    )

    started = time()
    levels = search!(Lazytree(phases, x), x, y, settings)
    nodes = reduce(vcat, levels[2:end])
    target_ids = Set([0, 1])
    exact_target_present = any(Set(get_phase_ids(node)) == target_ids for node in nodes)
    finite_residuals = all(isfinite(norm(node.residual)) for node in nodes)
    max_returned_phases = isempty(nodes) ? 0 : maximum(
        length(get_phase_ids(node)) for node in nodes
    )
    passed = !isempty(nodes) && exact_target_present && finite_residuals &&
             max_returned_phases <= depth

    result = Dict(
        "status" => passed ? "passed" : "failed",
        "gate_scope" => "API and numerical compatibility only",
        "scientific_parameter_selection" => false,
        "limitation" => "Exact two-phase fixture is not a sensitivity or accuracy benchmark",
        "private_truth_used" => false,
        "fixture_origin" => "CrystalTree installed package data/sticks.csv",
        "fixture_package_relative_path" => "CrystalTree/data/sticks.csv",
        "fixture_sha256" => bytes2hex(open(sha256, fixture)),
        "development_spectrum" => "normalized sum of official fixture phases 0 and 1",
        "phase_candidate_count" => length(phases),
        "returned_hypothesis_count" => length(nodes),
        "exact_target_hypothesis_present" => exact_target_present,
        "finite_residuals" => finite_residuals,
        "max_returned_phases" => max_returned_phases,
        "runtime_seconds" => time() - started,
        "parameters" => Dict(
            "std_noise" => std_noise,
            "mean_theta" => mean_theta,
            "std_theta" => std_theta,
            "maxiter" => maxiter,
            "tree_depth" => depth,
            "candidate_expansion_count" => expansion_count,
            "amorphous" => false,
            "background" => false,
            "background_length" => 5.0,
        ),
    )
    mkpath(dirname(abspath(ARGS[1])))
    open(ARGS[1], "w") do io
        JSON.print(io, result, 2)
        println(io)
    end
    println(JSON.json(result))
    passed || error("Independent CrystalTree parameter gate failed")
end

main()
