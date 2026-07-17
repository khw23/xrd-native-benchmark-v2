# Dara v3：x86_64 Slurm CPU 服务器运行

这个目录供“服务器没有 Codex/agent，只能手动执行命令”的情况使用。服务器必须是原生
`x86_64`/`amd64` Linux；Dara 的 BGMN 官方二进制主要依赖 CPU，GPU 不会明显加速。

DGX Spark 上运行 CrystalShift/CrystalTree、XERUS 和 Dara smoke 时，应阅读
`fig4/benchmark/REMOTE_RUN_GUIDE_V3.md`。本文只负责在普通 x86_64 CPU 服务器上安装并运行
Dara；两份说明使用的是同一个 Atomly-Core v3 盲测包。

## 1. 登录节点：克隆并建立环境

```bash
git clone https://github.com/khw23/xrd-native-benchmark-v2.git
cd xrd-native-benchmark-v2

git log -1 --oneline
test -f fig4/benchmark/datasets/atomly_core_v3/native_blind_package_v3.zip
test -f fig4/benchmark/prototypes/run_dara_native_v3.py

uname -m
eval "$(conda shell.bash hook)"
conda env create -f server_dara/environment.yml
conda activate xrd-dara-v3
python -c "import dara, ray, pymatgen; print('Dara environment OK')"
```

仓库已公开，因此这里使用 HTTPS 克隆，不要求服务器配置 GitHub SSH 公钥。默认分支 `main`
已经是 Atomly-Core v3，不再需要切换到旧的临时 v3 分支；两个 `test -f` 命令均应成功。

如果服务器上已经克隆过仓库，使用下面的命令更新到当前 `main`，不要重新克隆：

```bash
cd xrd-native-benchmark-v2
git switch main
git pull --ff-only origin main
git log -1 --oneline
```

如果环境已经存在，改用：

```bash
conda env update -n xrd-dara-v3 -f server_dara/environment.yml --prune
```

环境固定 Dara 1.3.0 的 `strict` 依赖组，避免重复 DGX smoke 中 Ray、pymatgen、NumPy 和
jenkspy 版本漂移的问题。

## 2. Slurm 资源设置

Dara runner 是“一个 Python/Ray 驱动进程 + 多个 BGMN refinement”，不是 64 个 MPI rank，
因此提交文件使用：

```text
--nodes=1
--ntasks=1
--cpus-per-task=64
```

不要使用示例 VASP 脚本中的 `--ntasks-per-node=64`，否则调度器会按 64 个独立任务理解资源，
但这里并没有启动 64 个 MPI 进程。oneAPI、MVAPICH 和 VASP 模块也与 Dara/BGMN 无关，四个
提交文件只执行 `module purge`，随后激活 `xrd-dara-v3`。

如果环境使用其他名字，提交时增加例如
`--export=ALL,CONDA_ENV_NAME=my-dara-env`；不设置时默认仍为 `xrd-dara-v3`。

默认队列是 `regular`。日志使用任务名和 job ID，例如 `dara_full_12345.out` 和
`dara_full_12345.err`，避免重复提交时覆盖旧记录。所有 `sbatch` 命令必须在仓库根目录执行。

## 3. 提交 COD 准备任务

```bash
sbatch server_dara/slurm_01_prepare.sbatch
```

该任务会先执行盲包完整性检查，再下载/整理 84 个元素体系的 COD 候选并生成审计报告。
若服务器已有 COD mirror：

```bash
sbatch --export=ALL,COD_ROOT=/absolute/path/to/COD_2024 \
  server_dara/slurm_01_prepare.sbatch
```

查看状态和日志：

```bash
squeue -u "$USER"
sacct -j JOB_ID --format=JobID,State,Elapsed,AllocCPUS,MaxRSS,ExitCode
```

对应的 `dara_prepare_JOBID.out` 必须显示 100 个样本、84 个唯一元素体系、`status: passed`，
并且候选审计成功。该步骤只使用公开的 `sample_elements`，不会读取私有 Atomly CIF 或真值。
完成后检查 `fig4/benchmark/method_inputs/cod_native_v3/audit_report.json`；候选数很大不是错误，
不能在看到预测或真值后手工删相。

## 4. 提交 smoke；通过后再提交全量

```bash
sbatch server_dara/slurm_02_smoke.sbatch
```

smoke 默认申请 16 CPU，使用 2 个 Ray 槽 × 每个 BGMN 8 线程。只有在产生非空
`predictions.csv`、`run_records.json` 中样本状态为 `ok`、并保存所选 CIF 后，才提交全量：

```bash
sbatch server_dara/slurm_03_full.sbatch
```

全量默认申请 64 CPU，使用 8 个 Ray 槽 × 每个 BGMN 8 线程。若实际只能申请 32 CPU，可覆盖
资源与并行参数：

```bash
sbatch --cpus-per-task=32 \
  --export=ALL,RAY_CPUS=4,BGMN_THREADS=8 \
  server_dara/slurm_03_full.sbatch
```

提交文件会检查 `RAY_CPUS × BGMN_THREADS <= SLURM_CPUS_PER_TASK`，防止过量并行。
`RPB=100` 表示扣除背景后的 profile residual 被判为最差/无有效拟合，不是“100 个峰”；若
所有单相都被拒绝，Dara 1.3.0 可能在自动 EPS2 初始化时出现 `rwp_sum=0`。此时保留失败记录，
不修改 RPB 规则或候选池来制造预测。

## 5. 提交打包任务并回传

```bash
sbatch server_dara/slurm_04_collect.sbatch
```

打包任务只需在全量任务正常结束后提交。回传生成的
`dara_atomly_core_v3_results.tar.gz` 和同名 `.sha256` 文件。其中只包含方法预测、运行记录、
失败日志和入选 CIF，不包含整个 COD cache。

如果集群支持依赖提交，也只能让打包任务依赖已经确认成功的全量 job；不要让 full 自动依赖
smoke，因为 smoke 结果需要人工检查：

```bash
sbatch --dependency=afterok:FULL_JOB_ID server_dara/slurm_04_collect.sbatch
```
