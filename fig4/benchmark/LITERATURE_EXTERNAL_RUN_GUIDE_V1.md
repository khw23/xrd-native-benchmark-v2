# Literature-External-v1: 78 条公开实验谱运行指南

本指南只负责外部文献实验集。Atomly-Core-100 保持独立，不把两者混成一个 headline
accuracy。78 条可在程序上一次遍历，但输出必须保留 `dataset_family`，最终分别报告四个家族。

## 1. 公共输入与校验

公开 runner 只读取：

- `fig4/benchmark/datasets/literature_external_v1/blind_package/patterns/`；
- `sample_manifest.csv` 中的 `sample_elements`、`dataset_family` 和采集元数据；
- 本文冻结的全局最多 3 相上限和仪器 profile 策略。

公开仓库不得出现 `private_scoring/`、答案相、逐样本真实相数、来源文件名或候选真值 CIF。

```bash
python fig4/benchmark/prototypes/validate_literature_external_public_v1.py
python fig4/benchmark/prototypes/audit_literature_external_scope_v1.py
```

预期为 78 条采集、58 个物理样品，家族计数 `10 + 8 + 40 + 20`，状态 `PASS`。
元素空间审计还应显示 46 个完整元素集合、46 个 XERUS 原生 OQMD 完整元素查询和 2,122 个所需
COD ID；任何一个数变化都表示公开 manifest 或数据库范围已改变，应建立新版本而不是覆盖 v1。

## 2. 解压并校验 COD/OQMD 离线缓存

缓存压缩包位于 `fig4/benchmark/server_transfer/literature_external_v1/`。在仓库根目录执行：

```bash
cd fig4/benchmark/method_inputs
tar -xzf ../server_transfer/literature_external_v1/cod_sparse_literature_external_v1_20260722.tar.gz
tar -xzf ../server_transfer/literature_external_v1/oqmd_optimade_cache_literature_external_v1_20260722.tar.gz
cd ../../..

python fig4/benchmark/prototypes/validate_literature_external_runtime_v1.py \
  --cod-root fig4/benchmark/method_inputs/cod_sparse_literature_external_v1 \
  --oqmd-root fig4/benchmark/method_inputs/oqmd_optimade_cache_literature_external_v1
```

COD 应有 2,122 个唯一 CIF；OQMD 应有 46 个完整元素系统。XERUS 官方
`multiquery` 对每个样品只发起一个完整元素列表的 OQMD 查询；这里不展开全部非空子集。
校验失败时不要启动方法。

## 3. 共享 COD 候选前端

Dara 和 CrystalShift/CrystalTree 共享同一份 Dara 2024 COD 索引语义，但分别运行自己的原生
搜索。已有 `cod-env` 可直接复用；新机器的环境安装仍按 `REMOTE_RUN_GUIDE_V3.md`。

```bash
cod-env/bin/python fig4/benchmark/prototypes/prepare_cod_candidate_sets_v3.py \
  --blind-root fig4/benchmark/datasets/literature_external_v1/blind_package \
  --cod-root fig4/benchmark/method_inputs/cod_sparse_literature_external_v1 \
  --output-root fig4/benchmark/method_inputs/cod_native_literature_external_v1 \
  --resume
```

这一步应生成 46 个完整元素空间目录。候选规则只由公开元素集合和冻结数据库索引决定，不能在
查看结果后删相。

## 4. CrystalShift + CrystalTree（DGX）

复用 Atomly-Core 已通过的 Julia 1.12.6、CrystalShift 和 CrystalTree 环境。先转换 2,122 个
COD CIF，再运行冻结的 `simple_fixed_sigma_0p1_maxiter512` baseline：

```bash
crystalshift-python/bin/python \
  fig4/benchmark/prototypes/prepare_crystalshift_cod_v3.py \
  --blind-root fig4/benchmark/datasets/literature_external_v1/blind_package \
  --cod-root fig4/benchmark/method_inputs/cod_native_literature_external_v1 \
  --converter fig4/benchmark/third_party/CrystalShift.jl/src/cif_to_input_file.py \
  --output-root fig4/benchmark/method_inputs/crystalshift_cod_literature_external_v1 \
  --snapshot-root fig4/benchmark/results/literature_external_v1/crystaltree_cod_frontend/input_preparation

julia +1.12.6 --compiled-modules=no \
  --project=fig4/benchmark/method_envs/crystalshift \
  fig4/benchmark/prototypes/run_crystaltree_cod_v3.jl \
  --blind-root fig4/benchmark/datasets/literature_external_v1/blind_package \
  --input-root fig4/benchmark/method_inputs/crystalshift_cod_literature_external_v1 \
  --cod-root fig4/benchmark/method_inputs/cod_native_literature_external_v1 \
  --result-root fig4/benchmark/results/literature_external_v1/crystaltree_cod_frontend \
  --maxiter 512 --resume
```

CrystalShift activation 不是质量分数或摩尔分数，不能用于 QPA 误差。该方法无仪器 profile
输入，记录为固定 pseudo-Voigt baseline。外部谱的原始范围并不统一；adapter 在任何背景扣除或
归一化之前，统一裁剪到 CrystalShift 候选模型相同的 `q=7–58 nm^-1`，再做既有 AsLS、归一化和
stride-4 下采样。每条输入/输出范围及哈希写入 `pattern_preprocessing_manifest.csv`，不按预测结果
选择窗口，也不把 5–150° 谱的模型范围外残差错误计入 CrystalTree。

## 5. XERUS（DGX）

复用 Atomly-Core 的 XERUS 1.1b、MongoDB 和 GSAS-II 环境。只修改现有本机配置中的
`gsas2.instr_params`，保留 MP API key 和 MongoDB 凭证，且不提交配置：

```bash
CONFIG=fig4/benchmark/third_party/Xerus/Xerus/settings/config.conf
sed -i '/^\[gsas2\]/,/^\[/ s#^instr_params *=.*#instr_params = inc/RigakuSi.instprm#' "$CONFIG"
grep -A3 '^\[gsas2\]' "$CONFIG"
```

确认 XERUS 源码中的 `Xerus/inc/RigakuSi.instprm` 存在，然后运行：

```bash
export GSASII_ROOT="$PWD/fig4/benchmark/third_party/GSAS-II"
export PYTHONPATH="$GSASII_ROOT:$GSASII_ROOT/backcompat:$PWD/fig4/benchmark/third_party/Xerus"
export MPLBACKEND=Agg

xerus-env/bin/python fig4/benchmark/prototypes/run_xerus_native_v3.py \
  --blind-root fig4/benchmark/datasets/literature_external_v1/blind_package \
  --instrument-profile fig4/benchmark/third_party/Xerus/Xerus/inc/RigakuSi.instprm \
  --oqmd-cache-root fig4/benchmark/method_inputs/oqmd_optimade_cache_literature_external_v1 \
  --result-root fig4/benchmark/results/literature_external_v1/xerus_native_default_profile \
  --n-jobs 4 --resume --retry-failures
```

这里冻结的是 XERUS 原生默认 `RigakuSi.instprm` baseline。Aeris 与 Philips 数据没有可核验的
GSAS-II calibrant profile，因此不得根据准确率事后手调。profile 不匹配作为限制随结果报告。

## 6. Dara（x86_64 Slurm 服务器）

复用 `server_dara` 已通过的 x86_64 环境和本机 GLIBC/BGMN 修补。profile 映射由公开仪器元数据
预先冻结：60 条 Aeris 使用源匹配 profile，8 条 IUCr 使用最接近的 bundled Philips surrogate，
10 条 AutoXRD 使用 bundled Rigaku surrogate。

```bash
python fig4/benchmark/prototypes/run_dara_native_v3.py \
  --blind-root fig4/benchmark/datasets/literature_external_v1/blind_package \
  --cod-root fig4/benchmark/method_inputs/cod_native_literature_external_v1 \
  --result-root fig4/benchmark/results/literature_external_v1/dara_cod_native \
  --instrument-profile-map fig4/benchmark/datasets/literature_external_v1/instrument_metadata/dara_profile_map.csv \
  --num-cpus 8 --bgmn-threads 8 --resume --retry-failures
```

Slurm 中仍使用一个 Python task 和 64 CPUs：`--ntasks=1 --cpus-per-task=64`。建议先加
`--sample-id LITV1_0001 --sample-id LITV1_0011 --sample-id LITV1_0019` 做三家族 smoke，确认
三个 profile 都可调用后，再提交上面的全量命令。

## 7. 结果目录与报告规则

三个 runner 均写入独立目录：

```text
fig4/benchmark/results/literature_external_v1/crystaltree_cod_frontend/
fig4/benchmark/results/literature_external_v1/xerus_native_default_profile/
fig4/benchmark/results/literature_external_v1/dara_cod_native/
```

保留 `predictions.csv`、`run_records.json`、环境/profile 记录、失败记录和最终入选 CIF。不要上传
整个 MongoDB、展开的 COD/OQMD cache 或任何 private truth。所有 error/timeout 仍在分母中；
最终按四个 `dataset_family` 分别统计，Dara 前驱体 2/8 min 以 `physical_sample_id` 作为配对重复，
不能当成 40 个独立物理样品。

每种方法完成后先运行不读取私有答案的结构校验：

```bash
python fig4/benchmark/prototypes/validate_literature_external_results_v1.py \
  --result-root fig4/benchmark/results/literature_external_v1/METHOD_RESULT_DIRECTORY
```

该脚本检查 78 个最新状态、manifest 哈希、公开/私有边界、预测 CIF 路径和分家族状态计数；它不
计算准确率。只有预测冻结并回传后，才在本机用未公开的 scoring package 评分。
