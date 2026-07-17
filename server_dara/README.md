# Dara v3：x86_64 CPU 服务器手动运行

这个目录供“服务器没有 Codex/agent，只能手动执行命令”的情况使用。服务器必须是原生
`x86_64`/`amd64` Linux；Dara 的 BGMN 官方二进制主要依赖 CPU，GPU 不会明显加速。

DGX Spark 上运行 CrystalShift/CrystalTree、XERUS 和 Dara smoke 时，应阅读
`fig4/benchmark/REMOTE_RUN_GUIDE_V3.md`。本文只负责在普通 x86_64 CPU 服务器上安装并运行
Dara；两份说明使用的是同一个 Atomly-Core v3 盲测包。

## 1. 克隆并安装

```bash
git clone https://github.com/khw23/xrd-native-benchmark-v2.git
cd xrd-native-benchmark-v2

git log -1 --oneline
test -f fig4/benchmark/datasets/atomly_core_v3/native_blind_package_v3.zip
test -f fig4/benchmark/prototypes/run_dara_native_v3.py

uname -m
conda env create -f server_dara/environment.yml
conda activate xrd-dara-v3
```

仓库已公开，因此这里使用 HTTPS 克隆，不要求服务器配置 GitHub SSH 公钥。默认分支 `main`
已经是 Atomly-Core v3，不再需要切换到旧的临时 v3 分支；两个 `test -f` 命令均应成功。

如果服务器上已经克隆过仓库，使用下面的命令更新到当前 `main`，不要重新克隆：

```bash
cd xrd-native-benchmark-v2
git switch main
git pull --ff-only origin main
git log -1 --oneline
```

`uname -m` 应输出 `x86_64`。环境固定 Dara 1.3.0 的 `strict` 依赖组，避免重复 DGX smoke
中 Ray、pymatgen、NumPy 和 jenkspy 版本漂移的问题。

## 2. 解压并验证盲包

```bash
python fig4/benchmark/prototypes/unpack_and_verify_v3.py
```

必须显示 100 个样本、84 个唯一元素体系和 `status: passed`。

## 3. 准备冻结 COD 候选

联网下载模式：

```bash
bash server_dara/01_prepare_candidates.sh
```

若服务器已有 COD mirror：

```bash
COD_ROOT=/absolute/path/to/COD_2024 bash server_dara/01_prepare_candidates.sh
```

这一步只使用公开的 `sample_elements`，不会读取私有 Atomly CIF 或真值。完成后检查
`fig4/benchmark/method_inputs/cod_native_v3/audit_report.json`；候选数很大不是错误，不能在
看到预测或真值后手工删相。

## 4. smoke 与全量

```bash
bash server_dara/02_smoke.sh
bash server_dara/03_full.sh
```

64 核服务器默认使用 8 个 Ray CPU 槽，每个 BGMN refinement 使用 8 线程，峰值约 64 线程。
如调度器只分配了 32 核，可执行：

```bash
RAY_CPUS=4 BGMN_THREADS=8 bash server_dara/03_full.sh
```

smoke 只有在产生非空 `predictions.csv`、`run_records.json` 中状态为 `ok`、并能保存所选 CIF
后才能进入全量。`RPB=100` 表示扣除背景后的 profile residual 被判为最差/无有效拟合，
不是“100 个峰”；若所有单相都被拒绝，Dara 1.3.0 可能在自动 EPS2 初始化时出现
`rwp_sum=0`。此时保留失败记录，不修改 RPB 规则或候选池来制造预测。

## 5. 打包回传

```bash
bash server_dara/04_collect_results.sh
```

回传生成的 `dara_atomly_core_v3_results.tar.gz`。其中只包含方法预测、运行记录、失败日志和
入选 CIF，不包含整个 COD cache。
