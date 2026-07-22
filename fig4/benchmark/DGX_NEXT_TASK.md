# DGX 下一轮任务：使用完整离线 OQMD cache 后台运行 XERUS 100 条

本文件给 DGX 上的 Codex 直接读取执行。工作分支固定为
`results/dgx-conversion-xerus-pilots`，继续更新现有 Draft PR #9；不要新建结果分支、clone、worktree
或 `*_v3`/`*_v4` 结果目录。

## 0. 已完成状态

- CrystalShift 转换已修复：冻结 COD 前端的 6,622/6,622 条候选全部完成最终转换，最终失败为 0。
- CrystalTree 100 条正式运行已完成：100/100 最新记录为 `status=ok`，统一使用
  `simple_fixed_sigma_0p1_maxiter512`。
- XERUS `XRDV3_0046` 离线 OQMD pilot 已完成。旧的 OQMD HTTP 502、GSAS-II 路径错误和
  `python tcif.py` 解释器错误只作为历史故障记录保留。
- 本轮不再运行低/中/高三档 smoke。用户已批准直接准备完整候选并后台运行 100 条。

不得读取或复制 Atomly 私有真值，不得根据预测结果修改数据库、参数、相数上限或候选规则。

## 1. 同步与前置检查

只在没有正在运行的 XERUS/CrystalTree 任务时同步：

```bash
cd /home/khw/projects/xrd/xrd-native-benchmark-v2-dgx-next
git status --short --branch
git switch results/dgx-conversion-xerus-pilots
git pull --ff-only origin results/dgx-conversion-xerus-pilots
python3 fig4/benchmark/prototypes/unpack_and_verify_v3.py
```

如果实际仓库路径不同，只替换第一行 `cd`。工作区不干净时先判断文件归属；不得使用
`reset --hard`、`clean -fdx` 或删除现有结果来绕开问题。

确认没有旧 writer：

```bash
pgrep -af 'run_xerus_native_v3.py|run_xerus_full_background_v3.sh' || true
```

若确有运行中的正式任务，停止本轮操作并向用户报告，不得启动第二个 writer。

## 2. 接收并校验完整 OQMD cache

用户会把以下文件传到 DGX：

```text
xerus_oqmd_cache_v3_full_20260722.tar.gz
xerus_oqmd_cache_v3_full_20260722.tar.gz.sha256
```

缓存必须解压到唯一固定位置：

```text
<repo>/fig4/benchmark/method_inputs/oqmd_optimade_cache_v3_full/
```

当前 DGX 对应绝对路径预计为：

```text
/home/khw/projects/xrd/xrd-native-benchmark-v2-dgx-next/fig4/benchmark/method_inputs/oqmd_optimade_cache_v3_full/
```

在仓库根目录执行：

```bash
CACHE_ARCHIVE=/path/to/xerus_oqmd_cache_v3_full_20260722.tar.gz
(cd "$(dirname "$CACHE_ARCHIVE")" && \
  sha256sum -c "$(basename "$CACHE_ARCHIVE").sha256")
mkdir -p fig4/benchmark/method_inputs
tar -xzf "$CACHE_ARCHIVE" -C fig4/benchmark/method_inputs

python3 - <<'PY'
import json
from pathlib import Path

root = Path('fig4/benchmark/method_inputs/oqmd_optimade_cache_v3_full')
manifest = json.loads((root / 'cache_manifest.json').read_text())
assert manifest['complete'] is True, manifest
assert manifest['requested_system_count'] == 470, manifest
assert manifest['complete_system_count'] == 470, manifest
assert manifest['failed_system_count'] == 0, manifest
print('OQMD_FULL_CACHE_OK', manifest['complete_system_count'])
PY
```

完整 cache 不提交 GitHub。GitHub 只保存运行产生的候选 manifest、预测、入选 CIF、环境信息和日志。

## 3. 固定环境与 MongoDB

继续复用 pilot 已验证的环境、配置和 MongoDB，不重装软件：

```bash
test -x xerus-env/bin/python
test -f fig4/benchmark/third_party/Xerus/Xerus/settings/config.conf
test -f fig4/benchmark/datasets/atomly_core_v3/native_blind_package_v3/instrument_metadata/GSASII_reference_profile.instprm

docker start xerus-mongo-oqmd-pilot >/dev/null 2>&1 || true
docker ps --filter name=xerus-mongo-oqmd-pilot
```

`config.conf` 的 `[mongodb]` 必须仍指向：

```ini
host = localhost:27018
user = xerus
password = xerus_pilot_v3
```

保留 DGX 本地已有的 Materials Project API key。不得把密码、API key、MongoDB volume、method
environment 或完整候选 cache 提交 GitHub。

## 4. 提交一个脱离 Codex 的后台全量任务

结果目录继续复用已有的：

```text
fig4/benchmark/results/atomly_core_v3/xerus_native_pilot_v2/
```

目录名保留历史 `pilot_v2` 是为了避免复制/分叉结果；本轮完成后它将同时包含 pilot 审计历史和
100 条正式最新输出。runner 的 `--resume --retry-failures` 会跳过已成功的 `XRDV3_0046`，重试旧失败
并继续其余样品。

启动命令：

```bash
mkdir -p fig4/benchmark/results/atomly_core_v3/xerus_native_pilot_v2/logs

nohup bash fig4/benchmark/prototypes/run_xerus_full_background_v3.sh \
  > fig4/benchmark/results/atomly_core_v3/xerus_native_pilot_v2/logs/full_background_launcher.log \
  2>&1 < /dev/null &

echo $! > fig4/benchmark/results/atomly_core_v3/xerus_native_pilot_v2/logs/full_background.pid
```

Codex 只做一次启动检查，不持续等待：

```bash
sleep 30
PID=$(cat fig4/benchmark/results/atomly_core_v3/xerus_native_pilot_v2/logs/full_background.pid)
ps -fp "$PID"
tail -n 80 fig4/benchmark/results/atomly_core_v3/xerus_native_pilot_v2/logs/full_background_launcher.log
```

若 PID 存活、日志已进入 cache 校验或 candidate-preparation 阶段，且没有 traceback、配置错误或
MongoDB 连接错误，Codex 立即向用户报告 PID、日志路径和当前阶段，然后结束任务，不要一直轮询消耗
token。运行慢本身不是错误。

用户之后可手动检查：

```bash
PID=$(cat fig4/benchmark/results/atomly_core_v3/xerus_native_pilot_v2/logs/full_background.pid)
ps -fp "$PID"
tail -n 100 fig4/benchmark/results/atomly_core_v3/xerus_native_pilot_v2/logs/full_background_launcher.log
```

成功时会生成：

```text
fig4/benchmark/results/atomly_core_v3/xerus_native_pilot_v2/logs/XERUS_FULL_COMPLETED
```

失败时会生成 `XERUS_FULL_FAILED`，并记录退出码。不要在失败作业尚存活时启动第二个任务。

## 5. 后台脚本的冻结流程

`run_xerus_full_background_v3.sh` 依次执行且只使用一个 writer：

1. 校验 470/470 个 OQMD 子体系 cache 完整；
2. 对全部 100 条执行 `--prepare-candidates-only`，用完整离线 OQMD cache，并将 MP/COD/ODBX
   原生候选写入固定 MongoDB；
3. 候选准备全部成功后，在相同 cache、MongoDB、仪器 profile、`n_jobs=4`、`n_runs=3` 和
   最大三相设置下执行 100 条正式 XERUS；
4. 所有状态使用 `--resume --retry-failures`，中断后可重新提交同一脚本续跑。

不做三档 smoke，不增加外层样品并发，不按候选规模或预测结果调整参数。

## 6. 完成后的回传

后台任务结束后，再让 DGX Codex 检查：

- 100 个样品是否各有最新 `status=ok`，失败必须保留；
- `predictions.csv` 是否每个样品只保留最新正式输出；
- 候选 manifest、入选 CIF 和 SHA-256 是否完整；
- 日志中 OQMD 是否全部来自 `frozen_local_optimade_cache`，不得出现新的 `oqmd.org` 请求；
- 不得读取私有真值或在 DGX 计算准确率。

只提交 runner、结果 manifest、预测、最终入选 CIF、校验和、环境记录与必要日志。不得提交完整 OQMD
cache、MongoDB、所有候选 CIF、API key 或私有答案。继续推回同一分支和 Draft PR #9。
