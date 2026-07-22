#!/bin/bash
#SBATCH --job-name=dara_lit_full
#SBATCH --partition=regular
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=64
#SBATCH --output=dara_lit_full_%j.out
#SBATCH --error=dara_lit_full_%j.err

set -euo pipefail
ulimit -s unlimited
ulimit -c unlimited
module purge
cd "${SLURM_SUBMIT_DIR:?Submit from the repository root}"

set +u
eval "$(conda shell.bash hook)"
conda activate "${CONDA_ENV_NAME:-xrd-dara-v3}"
set -u

export RAY_CPUS="${RAY_CPUS:-8}"
export BGMN_THREADS="${BGMN_THREADS:-8}"
test "$((RAY_CPUS * BGMN_THREADS))" -le "${SLURM_CPUS_PER_TASK:?}"
bash server_dara/literature_external_v1/03_full.sh
