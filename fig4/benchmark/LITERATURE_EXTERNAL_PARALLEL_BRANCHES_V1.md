# Literature-External-v1 并行分支约定

外部 78 条公开实验谱在两台设备上并行运行，但仍是同一个冻结数据版本。两个远端分支从同一
提交起点建立：

- `run/literature-external-dgx-v1`：仅运行和回传 CrystalShift/CrystalTree、XERUS；
- `run/literature-external-server-v1`：仅运行和回传 Dara。

两台设备不得互相切换或推送对方分支，也不得把运行中间状态写回 `main`。

## 结果目录所有权

DGX 只写：

```text
fig4/benchmark/results/literature_external_v1/crystaltree_cod_frontend/
fig4/benchmark/results/literature_external_v1/xerus_native_default_profile/
fig4/benchmark/results/literature_external_v1/logs/dgx/
fig4/benchmark/results/literature_external_v1/DGX_RUN_STATUS.md
```

x86_64 Slurm 服务器只写：

```text
fig4/benchmark/results/literature_external_v1/dara_cod_native/
fig4/benchmark/results/literature_external_v1/logs/server/
fig4/benchmark/results/literature_external_v1/SERVER_DARA_RUN_STATUS.md
```

解压后的 COD/OQMD cache、MongoDB、软件环境、API key 和 `private_scoring` 均不得提交。
允许提交预测、append-only 运行记录、失败记录、候选 manifest、最终入选 CIF、校验和、环境
信息和必要日志。

## 完成后合并

两个分支可以同时计算。每台设备只提交自己负责的结果目录和必要的 runner 修复。两条分支都
完成公开边界校验后，再依次通过 PR 合入 `main`；第二条分支在合并前同步最新 `main`。准确率
只在本机、预测冻结之后用私有评分数据计算。
