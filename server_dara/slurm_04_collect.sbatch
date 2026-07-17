#!/bin/bash
#SBATCH --job-name=dara_collect
#SBATCH --partition=regular
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --output=dara_collect_%j.out
#SBATCH --error=dara_collect_%j.err

set -euo pipefail
ulimit -s unlimited
ulimit -c unlimited
module purge

cd "${SLURM_SUBMIT_DIR:?Submit this job from the repository root}"
test -f server_dara/environment.yml
test "$(uname -m)" = "x86_64"

bash server_dara/04_collect_results.sh
