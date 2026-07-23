# Atomly-Core v3 原生数据库盲测：DGX 与服务器运行指南

> 当前状态（2026-07-22）：CrystalTree 100 条 `maxiter=512` baseline 和 XERUS 离线 OQMD 单样本
> pilot 已通过。下一轮不再做三档 smoke；按 `DGX_NEXT_TASK.md` 接收完整 470 子体系 OQMD cache，
> 然后提交一个脱离 Codex 的后台 XERUS 100 条任务。旧结果不得覆盖或删除。

## 0. 输入边界

所有方法只可读取：

- `native_blind_package_v3/patterns/`；
- `sample_manifest.csv` 中的精确 `sample_elements`；
- `instrument_metadata/`；
- 全局“最多 3 相”上限。

禁止向远端复制 Atomly 生成 CIF、私有相池、真实二相/三相标签、相比例或 Atomly--COD 真值表。
方法必须返回原生数据库 ID，最好同时保留最终入选 CIF。

## 1. 克隆或更新仓库并验证盲包

首次下载：

```bash
git clone https://github.com/khw23/xrd-native-benchmark-v2.git
cd xrd-native-benchmark-v2
git log -1 --oneline

python3 fig4/benchmark/prototypes/unpack_and_verify_v3.py
```

已经克隆过仓库：

```bash
cd xrd-native-benchmark-v2
git status --short --branch
git fetch origin
git log -1 --oneline

python3 fig4/benchmark/prototypes/unpack_and_verify_v3.py
```

只有 `git status` 确认工作区干净且没有任务运行时，才可切换分支或执行 `git pull --ff-only`。
若存在未提交结果、cache 或运行中的任务，应保留原目录，用新的 clone/worktree 做下一轮；禁止
`git reset --hard`、`git clean -fdx` 或删除旧的 `results/`。

默认分支 `main` 已经是 Atomly-Core v3；旧的临时 v3 分支已删除，不再需要手工切换。
如果 DGX 已经从该临时分支启动任务，不要在任务运行中途切换分支。只要下面的盲包哈希一致，
并且 `unpack_and_verify_v3.py` 通过，该次运行仍属于同一个 v3 benchmark；任务结束并保存结果后
再切回并更新 `main` 即可。合并 PR 会改变提交号，但不会因此改变已经冻结的 v3 输入。

预期：100 个样本、84 个唯一元素体系、`status: passed`。压缩包哈希必须为：

```text
dde24eb5b1553f005c5da99a4bd2adf242ba6360ced0f8e4fed42238835e6243
```

建议在远端新建结果分支，避免环境试验污染 runner 分支：

```bash
git switch -c results/dgx-atomly-core-v3
```

## 2. 共享 COD 前端：Dara 与 CrystalShift/CrystalTree

DGX 上先建立只负责 COD 获取/预处理的 Python 环境：

```bash
python3 -m venv cod-env
cod-env/bin/python -m pip install --upgrade pip
cod-env/bin/python -m pip install "dara-xrd[strict]==1.3.0"

cod-env/bin/python fig4/benchmark/prototypes/prepare_cod_candidate_sets_v3.py --resume
cod-env/bin/python fig4/benchmark/prototypes/audit_cod_candidate_sets_v3.py
cod-env/bin/python fig4/benchmark/prototypes/select_smoke_samples_v3.py
```

候选规则是：元素集合为公开 `sample_elements` 非空子集、随后通过 Dara COD 预处理的所有相。
v3 有 84 个唯一元素体系。`audit_report.json` 会报告候选数分布；候选很多不是错误，不能在查看
预测或真值后人工删减。若必须加入确定性 shortlist，必须先写清规则并冻结为新的方法版本。

## 3. DGX：CrystalShift + CrystalTree with COD front-end

Julia 官方建议使用 Juliaup；本 runner 固定 Julia 1.12.6 和本机 smoke 使用过的两个源码提交：

```bash
curl -fsSL https://install.julialang.org | sh -s -- --yes
export PATH="$HOME/.juliaup/bin:$PATH"
juliaup add 1.12.6

mkdir -p fig4/benchmark/method_envs/crystalshift
julia +1.12.6 --project=fig4/benchmark/method_envs/crystalshift -e '
using Pkg
Pkg.add(PackageSpec(url="https://github.com/MingChiangChang/CrystalShift.jl", rev="37155e71c166f952dbdba2607604e36d13feb8ef"))
Pkg.add(PackageSpec(url="https://github.com/MingChiangChang/CrystalTree.jl", rev="cfe9c7d48801de5c4f8e25b77e528ec408318119"))
Pkg.add("JSON")
'
```

准备 CIF 转换环境：

```bash
python3 -m venv crystalshift-python
crystalshift-python/bin/python -m pip install --upgrade pip
crystalshift-python/bin/python -m pip install numpy pandas scipy pymatgen xrayutilities
mkdir -p fig4/benchmark/third_party
git clone https://github.com/MingChiangChang/CrystalShift.jl \
  fig4/benchmark/third_party/CrystalShift.jl
git -C fig4/benchmark/third_party/CrystalShift.jl checkout \
  37155e71c166f952dbdba2607604e36d13feb8ef
```

转换脚本逐 CIF 记录失败，不会因一个坏 CIF 丢弃整个元素体系。旧版本曾只成功 5,591/6,622 条；
统一、与真值无关的修复已经使 6,622/6,622 条候选全部完成最终转换，结构验证失败和最终失败均为
0。正式输入和结果分别冻结在 `crystalshift_cod_v3_v2/` 与
`crystaltree_cod_frontend_v2/`。

```bash
crystalshift-python/bin/python \
  fig4/benchmark/prototypes/prepare_crystalshift_cod_v3.py \
  --converter fig4/benchmark/third_party/CrystalShift.jl/src/cif_to_input_file.py \
  --output-root fig4/benchmark/method_inputs/crystalshift_cod_v3_v2 \
  --snapshot-root fig4/benchmark/results/atomly_core_v3/crystaltree_cod_frontend_v2/input_preparation

julia +1.12.6 --compiled-modules=no \
  --project=fig4/benchmark/method_envs/crystalshift \
  fig4/benchmark/prototypes/run_crystaltree_cod_v3.jl \
  --input-root fig4/benchmark/method_inputs/crystalshift_cod_v3_v2 \
  --result-root fig4/benchmark/results/atomly_core_v3/crystaltree_cod_frontend_v2 \
  --sample-id XRDV3_0046 --sample-id XRDV3_0054 --sample-id XRDV3_0100
```

以下命令已经完成 100 条 `maxiter=512` baseline，只保留作 provenance，不再重复执行：

```bash
julia +1.12.6 --compiled-modules=no \
  --project=fig4/benchmark/method_envs/crystalshift \
  fig4/benchmark/prototypes/run_crystaltree_cod_v3.jl \
  --input-root fig4/benchmark/method_inputs/crystalshift_cod_v3_v2 \
  --result-root fig4/benchmark/results/atomly_core_v3/crystaltree_cod_frontend_v2 \
  --resume --maxiter 512
```

CrystalShift activation 只写入备注，不转换成摩尔或质量分数。DGX GPU 对当前 Julia 搜索实现
没有直接加速；它主要使用 CPU/内存，候选数与树深度决定耗时。

## 4. DGX：XERUS 原生数据库流程

XERUS 需要 MongoDB、Materials Project API key、COD/ODBX 网络访问和 GSAS-II。OQMD 网络曾持续
502，因此当前 pilot 通过 `--oqmd-cache-root` 使用仓库内经过校验的原始 OPTIMADE 响应；它不改变
OQMD 筛选条件或 XERUS 的结构转换。账号和 API key 只写在 DGX 本地，不提交仓库。当前应执行的
冻结命令以 `fig4/benchmark/DGX_NEXT_TASK.md` 为准。

先启动 MongoDB，例如：

```bash
docker run -d --name xerus-mongo -p 27017:27017 \
  -v "$PWD/mongodb-data:/data/db" mongo:6
```

安装冻结的 XERUS 1.1b 源码及兼容依赖：

```bash
python3 -m venv xerus-env
xerus-env/bin/python -m pip install --upgrade pip
mkdir -p fig4/benchmark/third_party
git clone https://github.com/pedrobcst/Xerus \
  fig4/benchmark/third_party/Xerus
git -C fig4/benchmark/third_party/Xerus checkout \
  53ed38b6d8437cf61abee270672bd33de75f15a3
git -C fig4/benchmark/third_party/Xerus apply \
  "$PWD/patches/xerus_gsasii_root.patch"
git -C fig4/benchmark/third_party/Xerus apply \
  "$PWD/patches/xerus_api_compat.patch"
xerus-env/bin/python -m pip install -r fig4/benchmark/xerus_requirements_compat.txt
xerus-env/bin/python -m pip install --no-deps -e fig4/benchmark/third_party/Xerus
cp fig4/benchmark/xerus_config.conf.template \
  fig4/benchmark/third_party/Xerus/Xerus/settings/config.conf
cp fig4/benchmark/datasets/atomly_core_v3/native_blind_package_v3/instrument_metadata/GSASII_reference_profile.instprm \
  fig4/benchmark/third_party/Xerus/Xerus/inc/benchmark_v3_reference.instprm
```

编辑最后一个 `config.conf`，只填本机 MongoDB 和 MP API key。XERUS 的旧内嵌 GSAS-II 在
ARM64 上不可靠，因此安装当前架构可用的官方 GSAS-II，并把根目录写入 `GSASII_ROOT`：

```bash
git clone https://github.com/AdvancedPhotonSource/GSAS-II \
  fig4/benchmark/third_party/GSAS-II
git -C fig4/benchmark/third_party/GSAS-II checkout \
  14dd93032174ba9b751539f3be64de69fcb33ab8
xerus-env/bin/python -m pip install -e fig4/benchmark/third_party/GSAS-II

export GSASII_ROOT="$PWD/fig4/benchmark/third_party/GSAS-II"
export PYTHONPATH="$GSASII_ROOT:$GSASII_ROOT/backcompat:$PWD/fig4/benchmark/third_party/Xerus"
export MPLBACKEND=Agg
```

若 GSAS-II 的 ARM64 扩展安装失败，停止并记录 infrastructure failure；不要改成私有 CIF
候选测试。此时 XERUS 也转到 x86_64 服务器更稳妥。

通用环境配置和 `XRDV3_0046` 离线 cache pilot 已完成。当前不再跑三个 pilot；把完整 OQMD cache
解压到 `fig4/benchmark/method_inputs/oqmd_optimade_cache_v3_full/` 后，按
`DGX_NEXT_TASK.md` 提交后台全量任务：

```bash
mkdir -p fig4/benchmark/results/atomly_core_v3/xerus_native_pilot_v2/logs
nohup bash fig4/benchmark/prototypes/run_xerus_full_background_v3.sh \
  > fig4/benchmark/results/atomly_core_v3/xerus_native_pilot_v2/logs/full_background_launcher.log \
  2>&1 < /dev/null &
```

后台脚本先对 100 条执行 candidate preparation，再执行正式分析，并统一使用 `--resume
--retry-failures --n-jobs 4`。Codex 启动后只检查 PID 和初始日志，不持续等待。中断时确认旧进程已
退出，再重新提交同一脚本续跑。

若测试多个外层并发进程，每个进程必须使用不同的 `--result-root`；当前 CSV/JSON 状态文件不支持
多进程同时写同一目录。完成后再用确定性脚本合并，不能直接拼接或覆盖。

XERUS 统一使用 `n_runs=3`；其结果表会在一相、二相、三相假设中按原生 Rwp 选择，不读取
逐样本真实相数。数据库提供者冻结为 XERUS 当前 MP/COD/OQMD/ODBX 流程，AFLOW 按其默认设置忽略。

## 5. Dara：DGX 仅复测，主全量优先 x86_64

DGX Spark 是 ARM64，而 DGX v2 smoke 通过 QEMU 执行 x86-64 BGMN，曾出现过度线程并发和
无有效单相结果。可以用严格环境做一次 v3 smoke：

```bash
cod-env/bin/python fig4/benchmark/prototypes/run_dara_native_v3.py \
  --sample-id XRDV3_0001 --num-cpus 2 --bgmn-threads 8 \
  --resume --retry-failures
```

若仍出现 `Exec format error`、所有候选 `RPB=100` 或自动 EPS2 的 `rwp_sum=0`，不要继续 100 条；
直接按仓库根目录 `server_dara/README.md` 转到原生 x86_64、64 核 CPU 服务器。

## 6. 结果回传

应提交：

```text
fig4/benchmark/results/atomly_core_v3/crystaltree_cod_frontend/
fig4/benchmark/results/atomly_core_v3/xerus_native/
fig4/benchmark/results/atomly_core_v3/dara_cod_native/
fig4/benchmark/results/atomly_core_v3/database_snapshots/
```

其中 `database_snapshots/` 和 XERUS 的 `candidate_manifests/` 只保存候选数据库 ID/元数据和
转换记录，不保存整库 CIF。不要提交 COD cache、XERUS MongoDB、Julia/Python 环境或任何私有真值。
远端执行：

```bash
git add fig4/benchmark/results/atomly_core_v3
git commit -m "Record atomly-core-v3 native benchmark results"
git push -u origin results/dgx-atomly-core-v3
```

所有 error/timeout 保留在 `run_records.json`，不能从 benchmark 分母中静默删除。
