# DGX 任务：Literature-External-v1 的 CrystalTree 与 XERUS

本文件给 DGX 上的 Codex 直接读取。固定工作分支为
`run/literature-external-dgx-v1`，只回传 CrystalShift/CrystalTree 和 XERUS；Dara 由
x86_64 Slurm 服务器在另一分支并行运行。

可以根据 DGX 的实际仓库路径、已安装环境路径、MongoDB 容器名和可用的用户级后台管理器做
必要适配，但不得改变候选规则、仪器 profile、CrystalTree 参数、XERUS `n_runs/n_jobs`、
全局三相上限或结果目录。任何代码兼容修复必须与真值无关，先做公开输入 smoke，记录 diff
和失败历史后再续跑。

## 1. 切换分支并检查边界

```bash
cd /home/khw/projects/xrd/xrd-native-benchmark-v2-dgx-next
git status --short --branch
git fetch origin
git switch run/literature-external-dgx-v1
git pull --ff-only origin run/literature-external-dgx-v1
git log -1 --oneline
```

若实际路径不同，只替换 `cd`。工作区不干净时先判断文件归属，不使用 `reset --hard`、
`clean -fdx`，也不另建 clone、worktree 或带 `_v2/_v3` 的结果目录。

确认没有旧 writer：

```bash
pgrep -af 'run_dgx_literature_external_v1.sh|run_xerus_native_v3.py|run_crystaltree_cod_v3.jl' || true
```

若已有同一任务在运行，停止本轮操作并报告。公开 runner 只能读取盲谱、`sample_elements`、
`dataset_family` 和采集元数据；不得读取或提交 `private_scoring`。

## 2. 解压并校验离线数据库

校验和必须在压缩包所在目录执行：

```bash
(cd fig4/benchmark/server_transfer/literature_external_v1 && \
  sha256sum -c cod_sparse_literature_external_v1_20260722.tar.gz.sha256 && \
  sha256sum -c oqmd_optimade_cache_literature_external_v1_20260722.tar.gz.sha256)

mkdir -p fig4/benchmark/method_inputs
tar -xzf \
  fig4/benchmark/server_transfer/literature_external_v1/cod_sparse_literature_external_v1_20260722.tar.gz \
  -C fig4/benchmark/method_inputs
tar -xzf \
  fig4/benchmark/server_transfer/literature_external_v1/oqmd_optimade_cache_literature_external_v1_20260722.tar.gz \
  -C fig4/benchmark/method_inputs

cod-env/bin/python fig4/benchmark/prototypes/validate_literature_external_public_v1.py
cod-env/bin/python fig4/benchmark/prototypes/validate_literature_external_runtime_v1.py \
  --cod-root fig4/benchmark/method_inputs/cod_sparse_literature_external_v1 \
  --oqmd-root fig4/benchmark/method_inputs/oqmd_optimade_cache_literature_external_v1
```

只有 COD `2,122/2,122`、OQMD `46/46`、78 acquisitions、58 physical samples 和
`status=PASS` 均满足时才继续。解压后的数据库不得提交。

## 3. 环境、profile 与 MongoDB 检查

复用 Atomly-Core 已通过的环境和源码，不重装：

```bash
test -x cod-env/bin/python
test -x crystalshift-python/bin/python
test -x xerus-env/bin/python
test -f fig4/benchmark/third_party/CrystalShift.jl/src/cif_to_input_file.py
test -f fig4/benchmark/third_party/Xerus/Xerus/inc/RigakuSi.instprm
julia +1.12.6 --version
```

XERUS 的本机 `config.conf` 保留已有 MongoDB 凭证和 Materials Project key，只把
`gsas2.instr_params` 固定为源码自带 profile：

```bash
CONFIG=fig4/benchmark/third_party/Xerus/Xerus/settings/config.conf
sed -i '/^\[gsas2\]/,/^\[/ s#^instr_params *=.*#instr_params = inc/RigakuSi.instprm#' "$CONFIG"
grep -A3 '^\[gsas2\]' "$CONFIG"

docker start xerus-mongo-oqmd-pilot >/dev/null 2>&1 || true
docker inspect -f '{{.State.Running}}' xerus-mongo-oqmd-pilot
```

若 DGX 当前容器名不同，可以使用已通过 Atomly-Core 的同一 XERUS MongoDB 实例并相应修改
本机未跟踪配置；不得把密码、API key 或 MongoDB volume 推到 GitHub。

## 4. 用用户级服务提交一次后台任务

不要让 Codex 前台持续等待，也不要使用 `nohup`。优先用 DGX 已验证的用户级 systemd 服务：

```bash
mkdir -p fig4/benchmark/results/literature_external_v1/logs/dgx
rm -f \
  fig4/benchmark/results/literature_external_v1/logs/dgx/DGX_LITERATURE_EXTERNAL_COMPLETED \
  fig4/benchmark/results/literature_external_v1/logs/dgx/DGX_LITERATURE_EXTERNAL_FAILED

systemd-run --user \
  --unit=xrd-litv1-dgx \
  --collect \
  --property="WorkingDirectory=$PWD" \
  /usr/bin/bash -lc \
  'exec bash fig4/benchmark/prototypes/run_dgx_literature_external_v1.sh >> fig4/benchmark/results/literature_external_v1/logs/dgx/launcher.log 2>&1'
```

启动后只检查一次：

```bash
systemctl --user status xrd-litv1-dgx --no-pager
tail -n 100 fig4/benchmark/results/literature_external_v1/logs/dgx/launcher.log
```

如果该 DGX 没有可用的 user systemd manager，Codex 可以改用该机已有且可脱离会话的用户级
任务管理器（例如 `tmux`），但仍只启动同一个脚本、一个 writer，并把 stdout/stderr 追加到
上述固定日志；不要退回前台长时间轮询或 `nohup`。

后台脚本顺序执行：

1. 校验公开输入和两个离线数据库；
2. 准备 46 个 COD 元素空间并转换全部 2,122 个 CIF；
3. 运行冻结的 CrystalTree `simple_fixed_sigma_0p1_maxiter512`；
4. 用完整离线 OQMD 加 XERUS 原生 MP/COD/ODBX 流程准备 78 条候选；
5. 用 `RigakuSi.instprm`、`n_runs=3`、`n_jobs=4` 和全局最多三相完成 XERUS。

脚本带 `--resume --retry-failures`，中断后重复提交同一脚本续跑。成功标志为
`logs/dgx/DGX_LITERATURE_EXTERNAL_COMPLETED`，失败标志为
`logs/dgx/DGX_LITERATURE_EXTERNAL_FAILED`。

## 5. 完成、校验与回传

```bash
cod-env/bin/python fig4/benchmark/prototypes/validate_literature_external_results_v1.py \
  --result-root fig4/benchmark/results/literature_external_v1/crystaltree_cod_frontend
cod-env/bin/python fig4/benchmark/prototypes/validate_literature_external_results_v1.py \
  --result-root fig4/benchmark/results/literature_external_v1/xerus_native_default_profile
```

两种方法都应有 78 个最新状态；失败和 timeout 必须保留，不能查看答案后调参。更新
`fig4/benchmark/results/literature_external_v1/DGX_RUN_STATUS.md`，只提交以下路径：

```bash
git add \
  fig4/benchmark/results/literature_external_v1/crystaltree_cod_frontend \
  fig4/benchmark/results/literature_external_v1/xerus_native_default_profile \
  fig4/benchmark/results/literature_external_v1/logs/dgx \
  fig4/benchmark/results/literature_external_v1/DGX_RUN_STATUS.md
git commit -m "Record Literature-External-v1 DGX results"
git push origin run/literature-external-dgx-v1
```

若产生了必要的真值无关兼容修复，先说明原因和验证，再显式加入相应 runner 文件。不要
`git add -A`，不要提交展开 cache、全部候选 CIF、环境目录、MongoDB、密钥或私有答案。
