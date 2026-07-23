#!/bin/bash
#SBATCH --job-name=dara_lit_collect
#SBATCH --partition=regular
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --output=fig4/benchmark/results/literature_external_v1/logs/server/dara_lit_collect_%j.out
#SBATCH --error=fig4/benchmark/results/literature_external_v1/logs/server/dara_lit_collect_%j.err

set -euo pipefail
module purge
cd "${SLURM_SUBMIT_DIR:?Submit from the repository root}"

bash server_dara/literature_external_v1/04_collect.sh
