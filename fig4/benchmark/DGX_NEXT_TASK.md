# DGX 下一轮任务：先修科学性门，再决定全量

本文件是给 DGX 上 Codex 直接读取和执行的任务单。先读：

- `fig4/benchmark/REMOTE_RUN_GUIDE_V3.md`
- `fig4/benchmark/results/atomly_core_v3/XERUS_CRYSTALTREE_RUN_ANALYSIS.md`
- PR #8 已有的 runner、failure manifest 和环境记录

## 1. 不可违反的边界

- 只用公开盲谱、`sample_elements`、仪器 profile 和全局最多 3 相；不要索取或读取私有真值。
- 不依据预测好坏、化学式或样本编号定向删除/修补候选。
- 不运行 Dara；这轮只处理 CrystalShift/CrystalTree 和 XERUS。
- 不删除或覆盖 PR #8 的诊断结果、cache、环境或运行日志。
- 禁止 `git reset --hard`、`git clean -fdx`、`rm -rf results`。
- 开始前先记录 `git status --short --branch`、当前提交和运行中的相关进程。

若当前目录有未提交文件或任务仍在运行，不要切分支或 pull；使用新的 clone/worktree。只读获取本文件可用：

```bash
git fetch origin results/local-xerus-crystaltree-smokes
git show origin/results/local-xerus-crystaltree-smokes:fig4/benchmark/DGX_NEXT_TASK.md
```

## 2. CrystalShift/CrystalTree：先修 adapter

现有转换为 5,591/6,622 条，1,031 条失败，当前 100 样本输出只保留为诊断快照。

执行要求：

1. 按失败类型分析 `conversion_failures.csv`，制定统一且与真值无关的 CIF 规范化规则。
2. 优先修复 atom label、CIF 语法和 converter 兼容问题；不能为特定样本或相写例外。
3. 对每个转换成功项核对数据库 ID、元素集合、晶胞参数、位点数/占位信息和空间群；任何实质改变都要记录。
4. 对 pymatgen 可解析但仍无法转换的候选给出明确类别和数量；不得静默丢弃。
5. 将新输入写到 `fig4/benchmark/method_inputs/crystalshift_cod_v3_v2/`，转换快照写到
   `fig4/benchmark/results/atomly_core_v3/crystaltree_cod_frontend_v2/input_preparation/`。
6. 先在上游官方示例或独立开发谱上检查 `std_noise`、峰位/宽度先验、`maxiter`、tree depth 和候选扩展数。
   不得用最终 100 条真值调参；记录采用值、来源和理由。
7. 只在转换完整性和独立参数门通过后，跑 XRDV3_0046、XRDV3_0054、XRDV3_0100 三个 smoke。
8. 先提交 audit 和 smoke 摘要，未获确认不要直接重跑全量 100 条。

新版 runner 支持独立目录：

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

CrystalShift activation 仍只作为模型内部量，不当作摩尔分数或质量分数。

## 3. XERUS：三档 pilot，不直接全量

固定：XERUS `53ed38b6d8437cf61abee270672bd33de75f15a3`，GSAS-II
`14dd93032174ba9b751539f3be64de69fcb33ab8`，仓库中的两个 XERUS patch 和同一仪器 profile。

顺序运行三档 pilot：

```bash
xerus-env/bin/python fig4/benchmark/prototypes/run_xerus_native_v3.py \
  --sample-id XRDV3_0046 --sample-id XRDV3_0054 --sample-id XRDV3_0100 \
  --n-jobs 4 \
  --result-root fig4/benchmark/results/atomly_core_v3/xerus_native_pilot_v2
```

若中断后继续，在同一命令末尾加 `--resume --retry-failures`；不要删掉已有状态文件重来。

记录每条的候选数、provider 超时/失败、总耗时、最终 ID/CIF、Rwp、质量分数和环境提交。不要从一个样本推导加速比。

如需测试两个样本外层并发，必须使用两个不同的 `--result-root`；同一 CSV/JSON 目录不能并发写。先做 2 路 × 每路 4 workers，比较网络错误率、内存和吞吐，再决定是否增加并发。未获确认不要启动 100 条全量。

## 4. 回传内容

在新的结果分支提交：

- 修复代码和统一规则说明；
- 转换前后计数、失败分类、结构保持校验；
- 三档 CrystalTree smoke；
- 三档 XERUS pilot；
- 环境版本、提交哈希、命令、运行时间、失败记录和 checksums。

不要提交 API key、MongoDB、方法环境、整库 cache 或私有真值。完成后创建 draft PR，并在说明中明确：哪些只是诊断，哪些门已通过，是否建议全量。
