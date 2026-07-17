#!/bin/bash
#SBATCH --job-name=dara_prepare
#SBATCH --partition=regular
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --output=dara_prepare_%j.out
#SBATCH --error=dara_prepare_%j.err

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

python -u fig4/benchmark/prototypes/unpack_and_verify_v3.py
bash server_dara/01_prepare_candidates.sh
