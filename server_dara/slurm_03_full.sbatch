#!/bin/bash
#SBATCH --job-name=dara_full
#SBATCH --partition=regular
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=64
#SBATCH --output=dara_full_%j.out
#SBATCH --error=dara_full_%j.err

set -euo pipefail
ulimit -s unlimited
ulimit -c unlimited
module purge

cd "${SLURM_SUBMIT_DIR:?Submit this job from the repository root}"
test -f server_dara/environment.yml
test "$(uname -m)" = "x86_64"

set +u
eval "$(conda shell.bash hook)"
conda activate "${CONDA_ENV_NAME:-xrd-dara-v3}"
set -u

export RAY_CPUS="${RAY_CPUS:-8}"
export BGMN_THREADS="${BGMN_THREADS:-8}"
requested_threads=$((RAY_CPUS * BGMN_THREADS))
test "$requested_threads" -le "${SLURM_CPUS_PER_TASK:?}"

bash server_dara/03_full.sh
