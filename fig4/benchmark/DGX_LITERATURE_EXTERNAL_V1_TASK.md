# DGX 后续任务：Literature-External-v1 的 CrystalTree 与 XERUS

本文件是 78 条外部公开实验谱的后续任务说明。当前 Atomly-Core-100 XERUS 后台任务运行期间，
不要执行本文件，也不要切换其工作分支。待用户确认 Atomly 任务已结束、外部准备分支已合并后，
在同一个仓库中顺序运行下面两种方法；无需新 clone 或新 worktree。

## 1. 同步与公共边界检查

```bash
cd /home/khw/projects/xrd/xrd-native-benchmark-v2-dgx-next
git status --short --branch
git switch main
git pull --ff-only origin main
python3 fig4/benchmark/prototypes/validate_literature_external_public_v1.py
```

若实际路径不同，只替换 `cd`。工作区不干净或仍有 Atomly writer 时停止并报告，不使用
`reset --hard` 或另建结果副本：

```bash
pgrep -af 'run_xerus_native_v3.py|run_crystaltree_cod_v3.jl|run_xerus_full_background_v3.sh' || true
```

公开包只给 78 张谱、元素空间和采集元数据；不读取或复制 `private_scoring`，不提供逐样品相数、
答案相或真值 CIF。

## 2. 解压并校验离线数据库

```bash
cd fig4/benchmark/method_inputs
sha256sum -c ../server_transfer/literature_external_v1/cod_sparse_literature_external_v1_20260722.tar.gz.sha256
sha256sum -c ../server_transfer/literature_external_v1/oqmd_optimade_cache_literature_external_v1_20260722.tar.gz.sha256
tar -xzf ../server_transfer/literature_external_v1/cod_sparse_literature_external_v1_20260722.tar.gz
tar -xzf ../server_transfer/literature_external_v1/oqmd_optimade_cache_literature_external_v1_20260722.tar.gz
cd ../../..

python3 fig4/benchmark/prototypes/validate_literature_external_runtime_v1.py \
  --cod-root fig4/benchmark/method_inputs/cod_sparse_literature_external_v1 \
  --oqmd-root fig4/benchmark/method_inputs/oqmd_optimade_cache_literature_external_v1
```

只在校验显示 COD 2,122/2,122、OQMD 46/46、`status=PASS` 时继续。

## 3. 共享 COD 前端与 CrystalShift 转换的前置检查

复用 Atomly 已验证的 `cod-env`、`crystalshift-python`、Julia 1.12.6 及源码提交，不重装环境。
这里只检查，不在 Codex 前台执行 2,122 个 CIF 的转换：

```bash
test -x cod-env/bin/python
test -x crystalshift-python/bin/python
test -f fig4/benchmark/third_party/CrystalShift.jl/src/cif_to_input_file.py
julia +1.12.6 --version
```

后台脚本会先生成 46 个元素空间，再对全部 2,122 个 CIF 给出转换状态；失败不能静默删除。若出现统一的
解析问题，只能按 Atomly 已采用的真值无关 normalization 规则修复并记录，不能查看答案后筛候选。
还必须生成 78 行 `pattern_preprocessing_manifest.csv`；所有谱在背景扣除前统一裁剪到候选模型的
`q=7–58 nm^-1`，原始与输出范围、点数和 SHA-256 均须保留。

## 4. 提交一个脱离 Codex 的顺序后台任务

把 XERUS 的 `config.conf` 中仅 `gsas2.instr_params` 改回源码自带的
`Xerus/inc/RigakuSi.instprm`；不要覆盖 MongoDB 配置或 DGX 本地 Materials Project key：

```bash
CONFIG=fig4/benchmark/third_party/Xerus/Xerus/settings/config.conf
sed -i '/^\[gsas2\]/,/^\[/ s#^instr_params *=.*#instr_params = inc/RigakuSi.instprm#' "$CONFIG"
grep -A3 '^\[gsas2\]' "$CONFIG"
```

预期只显示 `instr_params = inc/RigakuSi.instprm`；runner 还会做字节级 profile 哈希检查。继续
复用 Atomly pilot 的容器，不新建数据库实例：

```bash
docker start xerus-mongo-oqmd-pilot >/dev/null 2>&1 || true
docker ps --filter name=xerus-mongo-oqmd-pilot
```

本地 OQMD cache 只替代不稳定的 OQMD OPTIMADE 网络调用；XERUS 仍按其原生流程访问
MP/COD/ODBX。2,122-CIF sparse COD 包只服务 Dara 与 CrystalShift/CrystalTree，不注入 XERUS，
避免把三种方法强行改成同一候选库。然后启动：

```bash
mkdir -p fig4/benchmark/results/literature_external_v1/logs
nohup bash fig4/benchmark/prototypes/run_dgx_literature_external_v1.sh \
  > fig4/benchmark/results/literature_external_v1/logs/dgx_external_launcher.log \
  2>&1 < /dev/null &
echo $! > fig4/benchmark/results/literature_external_v1/logs/dgx_external_launcher.pid
```

Codex 只做一次启动检查后结束，不持续等待：

```bash
sleep 30
PID=$(cat fig4/benchmark/results/literature_external_v1/logs/dgx_external_launcher.pid)
ps -fp "$PID"
tail -n 80 fig4/benchmark/results/literature_external_v1/logs/dgx_external_launcher.log
```

脚本顺序执行 COD 候选准备、CrystalShift 转换、冻结的 CrystalTree
`simple_fixed_sigma_0p1_maxiter512`，再先为 78 条谱完成 XERUS
原生候选准备，最后执行 `RigakuSi.instprm`、完整离线 OQMD、`n_jobs=4` baseline。它不会运行三档 smoke，也不会读取
私有答案或按结果调参。成功标志为 `logs/DGX_LITERATURE_EXTERNAL_COMPLETED`；失败标志为
`logs/DGX_LITERATURE_EXTERNAL_FAILED`。

## 5. 回传规则

保留两个结果目录的 `predictions.csv`、`run_records.json`、候选 manifest、环境/profile 信息、
最终入选 CIF 和必要日志。不要提交解压后的 COD/OQMD、MongoDB、完整候选 CIF、API key 或
`private_scoring`。78 条可以一次运行，但最终仍按四个 `dataset_family` 分开报告，失败/timeout
保留在各家族分母中。

回传前分别运行：

```bash
python3 fig4/benchmark/prototypes/validate_literature_external_results_v1.py \
  --result-root fig4/benchmark/results/literature_external_v1/crystaltree_cod_frontend
python3 fig4/benchmark/prototypes/validate_literature_external_results_v1.py \
  --result-root fig4/benchmark/results/literature_external_v1/xerus_native_default_profile
```
