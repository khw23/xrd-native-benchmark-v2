# XRD native-workflow benchmark runner v3

跨设备运行 Atomly-Core v3 的公开 runner 仓库。当前只包含：

- 100 条盲谱压缩包及精确样本元素并集；
- CrystalShift + CrystalTree、XERUS、Dara 的原生/声明式数据库 runner；
- DGX ARM64 失败诊断和 x86_64 CPU 服务器 Slurm 运行包。

仓库不包含 Atomly 生成 CIF、真实相数、真实物相、相比例、难度标签或 Atomly--COD 私有判分表。

DGX 运行前阅读 [REMOTE_RUN_GUIDE_V3.md](fig4/benchmark/REMOTE_RUN_GUIDE_V3.md)；x86_64
Slurm 服务器运行 Dara 时阅读 [server_dara/README.md](server_dara/README.md)。

## 冻结输入

- 数据集：`atomly_core_v3`，100 条（50 二相 + 50 三相），逐样本相数隐藏。
- 全局上限：最多 3 相。
- 输入：盲谱 + `sample_elements` + 合成 profile 元数据。
- ZIP SHA-256：

```text
dde24eb5b1553f005c5da99a4bd2adf242ba6360ced0f8e4fed42238835e6243
```

## 方法命名

- `CrystalShift + CrystalTree with COD front-end`：CrystalShift 没有原生数据库检索层，COD 前端必须明确写入方法名。
- `XERUS 1.1b native database workflow`：使用 XERUS 自己的 MongoDB/MP/COD/OQMD/ODBX 查询与缓存流程。
- `Dara 1.3.0 + COD 2024`：使用 Dara 的 COD 前端和 BGMN 定量精修。

历史 DGX Dara smoke 见 `docs/legacy/DARA_V2_SMOKE_DIAGNOSTIC.md`。该记录解释了适配器错误、
ARM64 上 QEMU 执行 x86-64 BGMN、`RPB=100` 和 `rwp_sum=0`，但不包含可用于 v3 判分的真值。
