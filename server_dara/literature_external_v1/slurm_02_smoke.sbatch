#!/bin/bash
#SBATCH --job-name=dara_lit_smoke
#SBATCH --partition=regular
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --output=dara_lit_smoke_%j.out
#SBATCH --error=dara_lit_smoke_%j.err

set -euo pipefail
ulimit -s unlimited
ulimit -c unlimited
module purge
cd "${SLURM_SUBMIT_DIR:?Submit from the repository root}"

set +u
eval "$(conda shell.bash hook)"
conda activate "${CONDA_ENV_NAME:-xrd-dara-v3}"
set -u

export RAY_CPUS="${RAY_CPUS:-2}"
export BGMN_THREADS="${BGMN_THREADS:-8}"
test "$((RAY_CPUS * BGMN_THREADS))" -le "${SLURM_CPUS_PER_TASK:?}"
bash server_dara/literature_external_v1/02_smoke.sh
