# Dara：在 x86_64 Slurm 上运行 Literature-External-v1

本分支固定为 `run/literature-external-server-v1`，只运行外部 78 条公开实验谱的 Dara。
DGX 在另一分支并行运行 CrystalTree 与 XERUS。服务器继续复用已经通过 Atomly-Core smoke 的
`xrd-dara-v3`、用户目录 glibc 2.29 和已修补 BGMN，不重新安装环境。

## 1. 克隆或更新服务器分支

首次使用：

```bash
git clone https://github.com/khw23/xrd-native-benchmark-v2.git
cd xrd-native-benchmark-v2
git switch run/literature-external-server-v1
git log -1 --oneline
```

已有仓库：

```bash
cd xrd-native-benchmark-v2
git status --short --branch
git fetch origin
git switch run/literature-external-server-v1
git pull --ff-only origin run/literature-external-server-v1
git log -1 --oneline
```

不要在此分支运行 DGX 方法，也不要用 `reset --hard`、`clean -fdx` 或另建结果目录绕过已有
状态。所有 `sbatch` 命令都在仓库根目录提交。

## 2. 解压 COD 并做公开边界检查

```bash
(cd fig4/benchmark/server_transfer/literature_external_v1 && \
  sha256sum -c cod_sparse_literature_external_v1_20260722.tar.gz.sha256)

mkdir -p fig4/benchmark/method_inputs
tar -xzf \
  fig4/benchmark/server_transfer/literature_external_v1/cod_sparse_literature_external_v1_20260722.tar.gz \
  -C fig4/benchmark/method_inputs

eval "$(conda shell.bash hook)"
conda activate xrd-dara-v3
python fig4/benchmark/prototypes/validate_literature_external_public_v1.py
python fig4/benchmark/prototypes/validate_literature_external_runtime_v1.py \
  --cod-root fig4/benchmark/method_inputs/cod_sparse_literature_external_v1
```

预期为 78 acquisitions、58 physical samples、四个家族 `10 + 8 + 40 + 20`、COD
`2,122/2,122` 且 `status=PASS`。公开包不含答案、逐样品真实相数或真值 CIF。

## 3. 已知服务器兼容问题的前置门

提交脚本已对先前问题做固定处理：

- Conda 激活前暂时关闭 `set -u`，避免
  `qt-main_activate.sh: QT_XCB_GL_INTEGRATION: unbound variable`；
- 不设置全局新 glibc `LD_LIBRARY_PATH`，防止破坏 shell/Conda；
- 每次 prepare、smoke、full 都检查 `$HOME/opt/glibc-2.29` 的 loader、BGMN `teil`
  解释器和动态库映射；
- 新 loader 本身不得含 RPATH/RUNPATH，从而避免
  `elf_get_dynamic_info: info[DT_RPATH] == NULL` 断言。

`slurm_01_prepare.sbatch` 的开头会输出 `DARA_LITV1_PREFLIGHT_PASS`。如果前置门失败，不要提交
smoke。若错误只说明 loader 或 BGMN RPATH 被后续 Conda 更新覆盖，可运行一次修复任务：

```bash
REPAIR_JOB=$(sbatch --parsable \
  server_dara/literature_external_v1/slurm_00_repair_bgmn.sbatch)
echo "$REPAIR_JOB"
```

修复任务要求服务器上仍有之前建立的 `xrd-glibc229-build` 环境和
`$HOME/opt/glibc-2.29`；成功标志为 `BGMN_LOADER_RPATH_REPAIR_SUCCESS`。它不重编译 glibc。
若 loader 目录本身不存在，再使用之前已验证的完整 glibc 2.29 构建流程，不能用系统 glibc
2.17 直接运行 Dara 随包 BGMN。

## 4. 提交候选准备

先建立 Slurm 日志目录：

```bash
mkdir -p fig4/benchmark/results/literature_external_v1/logs/server
PREP_JOB=$(sbatch --parsable \
  server_dara/literature_external_v1/slurm_01_prepare.sbatch)
echo "$PREP_JOB"
```

检查：

```bash
sacct -j "$PREP_JOB" --format=JobID,State,Elapsed,AllocCPUS,MaxRSS,ExitCode
tail -n 100 \
  "fig4/benchmark/results/literature_external_v1/logs/server/dara_lit_prepare_${PREP_JOB}.out"
tail -n 100 \
  "fig4/benchmark/results/literature_external_v1/logs/server/dara_lit_prepare_${PREP_JOB}.err"
```

`.out` 必须出现 `DARA_LITV1_PREFLIGHT_PASS`、公开包 PASS、COD 2,122 和 46 个完整元素空间；
末尾还必须出现：

```text
COD_CANDIDATE_PREPARATION_SUMMARY 46/46 systems successful
COD_CANDIDATE_PREPARATION_OK
```

同时要求 `State=COMPLETED`、`ExitCode=0:0`。`.err` 为空或仅有非致命 warning。

若旧日志出现 `Local copy of database not found` 并尝试访问
`www.crystallography.net`，说明运行的是修复前的相对路径版本。更新本分支后直接重新提交
`slurm_01_prepare.sbatch`；`--resume` 会重试没有 `_SUCCESS.json` 的 46 个失败元素空间，不需要
删除旧输出或重新解压 COD。

## 5. 三 profile smoke

准备成功后提交：

```bash
SMOKE_JOB=$(sbatch --parsable \
  server_dara/literature_external_v1/slurm_02_smoke.sbatch)
echo "$SMOKE_JOB"
```

smoke 固定检查：

- `LITV1_0001`：AutoXRD / Rigaku surrogate；
- `LITV1_0011`：IUCr / Philips surrogate；
- `LITV1_0019`：Dara / Aeris source-matched。

```bash
sacct -j "$SMOKE_JOB" --format=JobID,State,Elapsed,AllocCPUS,MaxRSS,ExitCode
tail -n 120 \
  "fig4/benchmark/results/literature_external_v1/logs/server/dara_lit_smoke_${SMOKE_JOB}.out"
tail -n 120 \
  "fig4/benchmark/results/literature_external_v1/logs/server/dara_lit_smoke_${SMOKE_JOB}.err"
```

三个样品的最新 `run_records.json` 状态都应为 `ok`，profile 必须与
`dara_profile_map.csv` 一致。失败时保留日志，不根据答案修改 profile、候选池、RPB 门或三相
上限。

## 6. 全量、校验和回传

smoke 人工确认后：

```bash
FULL_JOB=$(sbatch --parsable \
  server_dara/literature_external_v1/slurm_03_full.sbatch)
echo "$FULL_JOB"
```

全量使用一个 Python/Ray task、64 CPUs、8 个 Ray worker × 每个 BGMN 8 线程，不是 64 个
MPI rank。检查：

```bash
squeue -u "$USER"
sacct -j "$FULL_JOB" --format=JobID,State,Elapsed,AllocCPUS,MaxRSS,ExitCode
tail -n 120 \
  "fig4/benchmark/results/literature_external_v1/logs/server/dara_lit_full_${FULL_JOB}.out"
tail -n 120 \
  "fig4/benchmark/results/literature_external_v1/logs/server/dara_lit_full_${FULL_JOB}.err"
```

全量正常结束后：

```bash
python fig4/benchmark/prototypes/validate_literature_external_results_v1.py \
  --result-root fig4/benchmark/results/literature_external_v1/dara_cod_native

COLLECT_JOB=$(sbatch --parsable \
  server_dara/literature_external_v1/slurm_04_collect.sbatch)
echo "$COLLECT_JOB"
```

打包结果为 `dara_literature_external_v1_results.tar.gz` 及其 `.sha256`。随后更新
`fig4/benchmark/results/literature_external_v1/SERVER_DARA_RUN_STATUS.md`，提交固定结果路径：

```bash
git add \
  fig4/benchmark/results/literature_external_v1/dara_cod_native \
  fig4/benchmark/results/literature_external_v1/logs/server \
  fig4/benchmark/results/literature_external_v1/SERVER_DARA_RUN_STATUS.md
git commit -m "Record Literature-External-v1 Dara results"
git push origin run/literature-external-server-v1
```

不要 `git add -A`，不要提交展开的 COD、完整候选 CIF、Conda 环境或私有评分答案。78 条运行
可以统一提交，但最终必须按四个 `dataset_family` 分别报告；Dara 前驱体 2/8 min 是同一物理
样品的配对采集，不是 40 个独立样品。
