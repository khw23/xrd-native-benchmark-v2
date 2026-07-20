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

## 1. CrystalShift/CrystalTree：先纠正 128 iterations

论文正文没有规定唯一的 `maxiter`，但官方论文复现源码
`third_party/CrystalShift.jl/paper/AlFeLiO.jl` 对最接近本 benchmark 的 1--3 相合成任务使用
`maxiter=512`；`128` 只是 `OptimizationSettings` 的软件默认值。因此正式 runner 已改为默认 512。

先把原来的精确两相 fixture 作为 API/数值兼容门重跑；它不是准确率或参数优选证据：

```bash
mkdir -p fig4/benchmark/results/atomly_core_v3/crystaltree_cod_frontend_v2/parameter_gate
julia +1.12.6 --compiled-modules=no \
  --project=fig4/benchmark/method_envs/crystalshift \
  fig4/benchmark/prototypes/validate_crystaltree_parameter_gate.jl \
  fig4/benchmark/results/atomly_core_v3/crystaltree_cod_frontend_v2/parameter_gate/maxiter512_compatibility_gate.json
```

随后只用上游公开的 Al-Fe-Li-O paper fixture 做参数敏感性审计，不得读取 100 条私有真值：

1. 新建一个精简的 `validate_crystaltree_paper_fixture.jl`。
2. 从上游 `paper/data/AlFeLiO/` 按固定规则选择最前面的 4 个单相、4 个二相、4 个三相样本；
   选择规则在运行前固定，不根据预测结果调整。
3. 在相同候选、相同已发表先验和相同 12 条谱上比较 `maxiter=128` 与 `512`；记录完整相组合
   top-1、phase precision/recall、残差、运行时间和失败数。
4. 同时核对官方 paper script 的 Simple/EM、`std_noise`、峰宽/应变先验和 background 设置。
   现有 `std_noise=0.1` + Simple + background off 只来自 README 示例，不能再称为已经科学验证。
5. 将比较写入同一 `parameter_gate/` 下的一个 JSON 和一个 Markdown；不要生成新的结果根目录。

在完成上述公开开发集审计前不要跑 100 条全量。可以先用修正后的 512 在原目录定点替换三个 smoke：

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

只有公开开发集参数审计通过、三个 512 smoke 正常，才可在同一目录续跑剩余样本：

```bash
julia +1.12.6 --compiled-modules=no \
  --project=fig4/benchmark/method_envs/crystalshift \
  fig4/benchmark/prototypes/run_crystaltree_cod_v3.jl \
  --input-root fig4/benchmark/method_inputs/crystalshift_cod_v3_v2 \
  --result-root fig4/benchmark/results/atomly_core_v3/crystaltree_cod_frontend_v2 \
  --resume --maxiter 512
```

CrystalShift activation 仍是模型内部量，不得解释为摩尔分数或质量分数。

## 2. XERUS：为什么这次失败，以及正确续跑方式

之前 `XRDV3_0001` 不是一次无故障成功：它先后留下 MP API 兼容、COD 断连和 OQMD timeout 等
6 次失败，第 7 次才完成。此次三个 pilot 中 MP/COD 成功后，OQMD OPTIMADE 对每次请求持续返回
HTTP 502；XERUS 原生 `multiquery` 串行调用 MP、COD、OQMD、ODBX，任一 provider 抛异常就不会把
该元素子系统写入 MongoDB，所以整个分析在模拟/精修前终止。这是外部 provider gate，不是谱线
扰动导致的识别失败。

不要把 OQMD 加入忽略列表：那会改变候选协议，而且 XERUS 的 `ignore_provider` 本来也是下载后过滤，
不能修复下载阶段异常。先做 OQMD health check；只有接口恢复为 200 才继续。

接口恢复后，先用新增的 `--prepare-candidates-only` 在同一个 MongoDB 和同一个结果目录冻结候选。
先重试三档 pilot：

```bash
xerus-env/bin/python fig4/benchmark/prototypes/run_xerus_native_v3.py \
  --sample-id XRDV3_0046 --sample-id XRDV3_0054 --sample-id XRDV3_0100 \
  --prepare-candidates-only --resume --retry-failures --n-jobs 4 \
  --result-root fig4/benchmark/results/atomly_core_v3/xerus_native_pilot_v2
```

确认三条最新记录均为 `candidates_ready`，候选数非零，`candidate_manifests/` 含 provider、数据库 ID
和路径记录，并确认运行时没有新的联网请求后，再在同目录运行正式三个 pilot：

```bash
xerus-env/bin/python fig4/benchmark/prototypes/run_xerus_native_v3.py \
  --sample-id XRDV3_0046 --sample-id XRDV3_0054 --sample-id XRDV3_0100 \
  --resume --retry-failures --n-jobs 4 \
  --result-root fig4/benchmark/results/atomly_core_v3/xerus_native_pilot_v2
```

三个 pilot 必须都有最终 ID/CIF、Rwp、质量分数、候选清单和运行时间。随后先提交报告；不要直接跑
100 条。下一阶段应先按同样方式预取全部 100 条涉及的元素子系统，使正式识别阶段只读冻结的
MongoDB，再决定 1 路或 2 路计算。若 OQMD 仍不稳定，只报告 blocked，不重复消耗计算资源。

## 3. 回传与提交

更新现有 `DGX_PILOT_GATE_REPORT.md`，明确区分：旧 128 diagnostic、512 compatibility gate、
公开 paper-fixture 参数审计、候选冻结、正式 pilot。不要计算或推断 100 条 benchmark 准确率。

```bash
git status --short
git diff --check
git add fig4/benchmark/DGX_NEXT_TASK.md \
  fig4/benchmark/prototypes/run_crystaltree_cod_v3.jl \
  fig4/benchmark/prototypes/validate_crystaltree_parameter_gate.jl \
  fig4/benchmark/prototypes/run_xerus_native_v3.py \
  fig4/benchmark/results/atomly_core_v3
git commit -m "Validate CrystalTree parameters and freeze XERUS candidates"
git push origin HEAD:results/dgx-conversion-xerus-pilots
```

提交前确认没有密钥、环境目录、MongoDB、cache、整库 CIF 或私有 truth。
