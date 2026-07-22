#!/bin/bash
#SBATCH --job-name=dara_lit_prepare
#SBATCH --partition=regular
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --output=dara_lit_prepare_%j.out
#SBATCH --error=dara_lit_prepare_%j.err

set -euo pipefail
ulimit -s unlimited
ulimit -c unlimited
module purge
cd "${SLURM_SUBMIT_DIR:?Submit from the repository root}"

set +u
eval "$(conda shell.bash hook)"
conda activate "${CONDA_ENV_NAME:-xrd-dara-v3}"
set -u

bash server_dara/literature_external_v1/01_prepare_candidates.sh
