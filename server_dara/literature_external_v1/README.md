# Dara: Literature-External-v1 on x86_64 Slurm

本目录只运行 78 条公开实验谱，不包含 Atomly-Core-100。环境、BGMN/GLIBC 修补方法与
`server_dara/README.md` 相同；已经通过 Atomly-Core 的 `xrd-dara-v3` 环境不需要重装。

## 1. 更新并检查公开输入

在仓库根目录执行：

```bash
git switch main
git pull --ff-only origin main
python fig4/benchmark/prototypes/validate_literature_external_public_v1.py
```

只有在本分支合并到 `main` 后才运行以上命令。预期输出为 78 条 acquisition、58 个物理样品、
四个家族 `10 + 8 + 40 + 20`，且 `status=PASS`。公开包不含答案、逐样品真实相数或真值 CIF。

## 2. 解压 COD 离线包

```bash
cd fig4/benchmark/method_inputs
sha256sum -c ../server_transfer/literature_external_v1/cod_sparse_literature_external_v1_20260722.tar.gz.sha256
tar -xzf ../server_transfer/literature_external_v1/cod_sparse_literature_external_v1_20260722.tar.gz
cd ../../..
```

随后提交候选准备任务：

```bash
PREP_JOB=$(sbatch --parsable server_dara/literature_external_v1/slurm_01_prepare.sbatch)
echo "$PREP_JOB"
```

`dara_lit_prepare_JOBID.out` 必须显示公共包与 2,122 个 COD CIF 校验通过，并生成 46 个完整
元素空间目录。`.err` 为空或只有非致命 warning；`sacct` 的 `State` 为 `COMPLETED`、`ExitCode`
为 `0:0`。

## 3. 三种 profile smoke

准备任务成功后提交：

```bash
SMOKE_JOB=$(sbatch --parsable server_dara/literature_external_v1/slurm_02_smoke.sbatch)
echo "$SMOKE_JOB"
```

smoke 固定检查 `LITV1_0001`（AutoXRD/Rigaku surrogate）、`LITV1_0011`
（IUCr/Philips surrogate）和 `LITV1_0019`（Dara/Aeris source-matched）。三个样品的最新
`run_records.json` 状态都必须是 `ok`，且 profile 名与
`instrument_metadata/dara_profile_map.csv` 一致。失败时保留日志，不根据答案改 profile、候选池、
RPB 或三相上限。

## 4. 全量与回传

smoke 人工确认后提交全量：

```bash
FULL_JOB=$(sbatch --parsable server_dara/literature_external_v1/slurm_03_full.sbatch)
echo "$FULL_JOB"
```

检查状态：

```bash
squeue -u "$USER"
sacct -j "$FULL_JOB" --format=JobID,State,Elapsed,AllocCPUS,MaxRSS,ExitCode
tail -n 80 "dara_lit_full_${FULL_JOB}.out"
tail -n 80 "dara_lit_full_${FULL_JOB}.err"
```

全量结束后执行：

```bash
python fig4/benchmark/prototypes/validate_literature_external_results_v1.py \
  --result-root fig4/benchmark/results/literature_external_v1/dara_cod_native

COLLECT_JOB=$(sbatch --parsable \
  --dependency="afterok:${FULL_JOB}" \
  server_dara/literature_external_v1/slurm_04_collect.sbatch)
echo "$COLLECT_JOB"
```

回传 `dara_literature_external_v1_results.tar.gz` 与同名 `.sha256`。包内只有预测、运行记录、
必要日志和最终入选 CIF；不含展开的 2,122 个 COD CIF，也不含私有评分答案。
