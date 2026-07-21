# DGX 下一轮任务：参数复核、候选冻结、原目录续跑

本文件给 DGX 上的 Codex 直接读取执行。工作分支固定为
`results/dgx-conversion-xerus-pilots`，继续更新现有 draft PR #9；不要再建结果分支、clone、worktree
或 `*_v3`/`*_v4` 结果目录。

## 0. 同步规则

先读 `AGENTS.md`、`fig4/benchmark/benchmark_plan.md`、
`fig4/benchmark/REMOTE_RUN_GUIDE_V3.md` 和
`fig4/benchmark/results/atomly_core_v3/DGX_PILOT_GATE_REPORT.md`。

```bash
git status --short --branch
git rev-parse HEAD
git switch results/dgx-conversion-xerus-pilots
git pull --ff-only origin results/dgx-conversion-xerus-pilots
```

如果工作区不干净或仍有任务运行，先检查并提交属于本任务的已有结果；不要用 `reset --hard`、
`clean -fdx` 或另建目录绕开。出现冲突就停止并报告。

固定复用两个结果根目录：

- `fig4/benchmark/results/atomly_core_v3/crystaltree_cod_frontend_v2/`
- `fig4/benchmark/results/atomly_core_v3/xerus_native_pilot_v2/`

Git 历史保存旧诊断；当前 CSV/JSON 只保留每个样本最新的正式输出。环境、cache、MongoDB、整库 CIF、
API key 和私有真值不得提交。

## 当前立即执行：CrystalTree 100 条全量

提交 `e570ff2` 已完成并通过以下门：6,622 条 COD 候选完整转换、512-iteration
API/数值兼容门、公开 Al-Fe-Li-O paper-fixture maxiter 敏感性门，以及低/中/高候选规模的
三个 512-iteration smoke。用户已批准启动 CrystalTree 100 条全量。

正式配置冻结为 `simple_fixed_sigma_0p1_maxiter512`。不得读取私有真值，不得根据全量预测结果
修改先验、噪声、tree depth、候选扩展数或 phase-count 设置。只启动一个写入该结果目录的进程；
开始前先确认没有已有 `run_crystaltree_cod_v3.jl` 任务。

```bash
mkdir -p fig4/benchmark/results/atomly_core_v3/crystaltree_cod_frontend_v2/logs

julia +1.12.6 --compiled-modules=no \
  --project=fig4/benchmark/method_envs/crystalshift \
  fig4/benchmark/prototypes/run_crystaltree_cod_v3.jl \
  --input-root fig4/benchmark/method_inputs/crystalshift_cod_v3_v2 \
  --result-root fig4/benchmark/results/atomly_core_v3/crystaltree_cod_frontend_v2 \
  --resume --maxiter 512 \
  2>&1 | tee fig4/benchmark/results/atomly_core_v3/crystaltree_cod_frontend_v2/logs/full_maxiter512.log
```

这是可续跑命令：中断后使用完全相同的命令，不删除 CSV/JSON 或 selected CIF。重点观察大候选样本
`XRDV3_0099`（629）、`XRDV3_0003`/`XRDV3_0058`（540）和
`XRDV3_0001`/`XRDV3_0010`/`XRDV3_0078`（395）；运行时间长本身不是失败，先检查 CPU、日志和
`run_records.json` 是否继续更新。不要并发启动第二个写同一结果目录的任务。

完成后必须检查：100 个样本各有最新 `status=ok`、最新成功记录均为 `maxiter=512` 和同一
`configuration_id`、`predictions.csv`/`top_hypotheses.csv` 无重复当前输出、selected CIF 路径存在，
并重新生成 checksums。随后更新 `DGX_PILOT_GATE_REPORT.md` 为 full-run report，提交结果并推回
同一 `results/dgx-conversion-xerus-pilots` 分支。CrystalShift activation 仍不得解释为质量分数或
摩尔分数。

## 1. CrystalShift/CrystalTree：已完成的门控记录

本节只保留参数决定和审计 provenance；DGX 不要重复执行本节的 gate/smoke 命令，当前任务以
文档顶部“当前立即执行：CrystalTree 100 条全量”为准。

论文正文没有规定唯一的 `maxiter`，但官方论文复现源码
`third_party/CrystalShift.jl/paper/AlFeLiO.jl` 对最接近本 benchmark 的 1--3 相合成任务使用
`maxiter=512`；`128` 只是 `OptimizationSettings` 的软件默认值。因此正式 runner 已改为默认 512。

原来的精确两相 fixture 已作为 API/数值兼容门重跑；它不是准确率或参数优选证据：

```bash
mkdir -p fig4/benchmark/results/atomly_core_v3/crystaltree_cod_frontend_v2/parameter_gate
julia +1.12.6 --compiled-modules=no \
  --project=fig4/benchmark/method_envs/crystalshift \
  fig4/benchmark/prototypes/validate_crystaltree_parameter_gate.jl \
  fig4/benchmark/results/atomly_core_v3/crystaltree_cod_frontend_v2/parameter_gate/maxiter512_compatibility_gate.json
```

随后已只用上游公开的 Al-Fe-Li-O paper fixture 做参数敏感性审计，没有读取 100 条私有真值：

1. 新建一个精简的 `validate_crystaltree_paper_fixture.jl`。
2. 从上游 `paper/data/AlFeLiO/` 按固定规则选择最前面的 4 个单相、4 个二相、4 个三相样本；
   选择规则在运行前固定，不根据预测结果调整。
3. 在相同候选、相同已发表先验和相同 12 条谱上比较 `maxiter=128` 与 `512`；记录完整相组合
   top-1、phase precision/recall、残差、运行时间和失败数。
4. 同时核对官方 paper script 的 Simple/EM、`std_noise`、峰宽/应变先验和 background 设置。
   现有 `std_noise=0.1` + Simple + background off 只来自 README 示例，不能再称为已经科学验证。
5. 将比较写入同一 `parameter_gate/` 下的一个 JSON 和一个 Markdown；不要生成新的结果根目录。

上述公开开发集审计和三个 512 smoke 均已完成；以下命令仅作 provenance，不要重复执行：

```bash
julia +1.12.6 --compiled-modules=no \
  --project=fig4/benchmark/method_envs/crystalshift \
  fig4/benchmark/prototypes/run_crystaltree_cod_v3.jl \
  --input-root fig4/benchmark/method_inputs/crystalshift_cod_v3_v2 \
  --result-root fig4/benchmark/results/atomly_core_v3/crystaltree_cod_frontend_v2 \
  --resume --rerun-selected --maxiter 512 \
  --sample-id XRDV3_0046 --sample-id XRDV3_0054 --sample-id XRDV3_0100 \
  2>&1 | tee fig4/benchmark/results/atomly_core_v3/crystaltree_cod_frontend_v2/logs/maxiter512_three_tier_smoke.log
```

检查 `run_records.json` 中这三条各自最新的成功记录均为 `maxiter=512`，且 `predictions.csv` 和
`top_hypotheses.csv` 每个样本没有重复旧输出。旧 128 记录可留在 `run_records.json` 作为审计轨迹，
但报告中须标记为 superseded diagnostic。

公开开发集参数审计和三个 512 smoke 已通过；当前全量运行使用文档顶部已批准的命令：

```bash
julia +1.12.6 --compiled-modules=no \
  --project=fig4/benchmark/method_envs/crystalshift \
  fig4/benchmark/prototypes/run_crystaltree_cod_v3.jl \
  --input-root fig4/benchmark/method_inputs/crystalshift_cod_v3_v2 \
  --result-root fig4/benchmark/results/atomly_core_v3/crystaltree_cod_frontend_v2 \
  --resume --maxiter 512
```

CrystalShift activation 仍是模型内部量，不得解释为摩尔分数或质量分数。

## 2. XERUS：冻结 OQMD 传输后的单样本 pilot

之前的失败发生在候选下载阶段：MP/COD 成功后，OQMD OPTIMADE 持续返回 HTTP 502。它不是谱线
扰动导致的识别失败。不要忽略 OQMD；本仓库现已冻结 `XRDV3_0046` 所需的 7 个 OQMD 元素子系统
原始 OPTIMADE 响应，共 150 条结构记录：

- cache：`fig4/benchmark/method_inputs/oqmd_optimade_cache_v3_pilot/`
- 元素子系统：`Ag`、`Br`、`Cl`、`Ag-Br`、`Ag-Cl`、`Br-Cl`、`Ag-Br-Cl`
- 顶层 manifest 必须为 `complete=true`，且所有分页 SHA-256 通过。

这个 cache 只替代 OQMD 的不稳定网络传输；过滤条件仍是 XERUS 1.1b 原生使用的
`elements HAS ONLY ... AND _oqmd_stability<0.05`，OPTIMADE 到 pymatgen/CIF 的转换仍由 DGX 上的
XERUS/optimade-adapters 执行。MP、COD、ODBX 仍走 XERUS 原生数据库流程，不能用 Atomly CIF
代替候选库。

为防止旧的部分 MongoDB 状态让 pilot 被误判为完整，使用一个固定的独立 MongoDB 容器和 volume；
不要再创建更多临时数据库目录：

```bash
docker run -d --name xerus-mongo-oqmd-pilot -p 27018:27017 \
  -e MONGO_INITDB_ROOT_USERNAME=xerus \
  -e MONGO_INITDB_ROOT_PASSWORD=xerus_pilot_v3 \
  -v xerus-mongo-oqmd-pilot:/data/db mongo:6
```

若这个固定容器已经由同一 pilot 创建，使用 `docker start xerus-mongo-oqmd-pilot` 续用，不要再建
第二个。将 DGX 本地（不得提交）的 XERUS `config.conf` 中 `[mongodb]` 改为：

```ini
host = localhost:27018
user = xerus
password = xerus_pilot_v3
```

保留现有 MP API key 和 GSAS-II profile 设置。先只准备 `XRDV3_0046` 的候选；这一步可与
CrystalTree 全量并行，但不要再启动第二个 CrystalTree writer：

```bash
xerus-env/bin/python fig4/benchmark/prototypes/run_xerus_native_v3.py \
  --sample-id XRDV3_0046 \
  --prepare-candidates-only --resume --retry-failures --n-jobs 4 \
  --oqmd-cache-root fig4/benchmark/method_inputs/oqmd_optimade_cache_v3_pilot \
  --result-root fig4/benchmark/results/atomly_core_v3/xerus_native_pilot_v2
```

先检查 `XRDV3_0046` 最新记录为 `candidates_ready`、候选数非零，`candidate_manifests/` 含 provider、
数据库 ID 和 CIF 路径，并记录 `oqmd_source=frozen_local_optimade_cache`、cache manifest SHA-256。
日志中不应出现对 `oqmd.org` 的 HTTP 请求；MP/COD/ODBX 联网仍属预期。随后在同一 cache、MongoDB
和结果目录运行这一个正式 pilot：

```bash
xerus-env/bin/python fig4/benchmark/prototypes/run_xerus_native_v3.py \
  --sample-id XRDV3_0046 \
  --resume --retry-failures --n-jobs 4 \
  --oqmd-cache-root fig4/benchmark/method_inputs/oqmd_optimade_cache_v3_pilot \
  --result-root fig4/benchmark/results/atomly_core_v3/xerus_native_pilot_v2
```

这一个 pilot 必须得到最终数据库 ID/CIF、Rwp、XERUS 报告的质量分数、候选清单和运行时间。
只在 `XRDV3_0046` 的候选门及正式运行都通过后报告结果；不要继续另外两条或 100 条。下一阶段再用
同一个下载器和固定 cache 根目录扩展全部 benchmark 所需元素子系统，并重新冻结完整候选快照。

## 3. 回传与提交

更新现有 `DGX_PILOT_GATE_REPORT.md`，明确区分：旧 128 diagnostic、512 compatibility gate、
公开 paper-fixture 参数审计、候选冻结、正式 pilot。不要计算或推断 100 条 benchmark 准确率。

```bash
git status --short
git diff --check
git add fig4/benchmark/DGX_NEXT_TASK.md \
  fig4/benchmark/REMOTE_RUN_GUIDE_V3.md \
  fig4/benchmark/method_inputs/oqmd_optimade_cache_v3_pilot \
  fig4/benchmark/prototypes/download_oqmd_optimade_cache_v3.py \
  fig4/benchmark/prototypes/run_crystaltree_cod_v3.jl \
  fig4/benchmark/prototypes/validate_crystaltree_parameter_gate.jl \
  fig4/benchmark/prototypes/run_xerus_native_v3.py \
  fig4/benchmark/results/atomly_core_v3
git commit -m "Validate CrystalTree parameters and freeze XERUS candidates"
git push origin HEAD:results/dgx-conversion-xerus-pilots
```

提交前确认没有密钥、环境目录、MongoDB、cache、整库 CIF 或私有 truth。
