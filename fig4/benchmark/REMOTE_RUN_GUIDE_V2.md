# Atomly-core-v2 原生数据库盲测：安装与远程运行

## 输入边界

主测试只使用：

- `datasets/atomly_core_v2/native_blind_package_v2/patterns/`；
- `sample_manifest.csv` 中的 `sample_elements`；
- Cu Kα 与 `instrument_metadata/`；
- 对所有样本统一的“最多 3 相”上限。

禁止把私有 84 个 Atomly 生成 CIF、逐样本相数或真值表复制到远程仓库。方法输出最好保留所选数据库 ID 和 CIF 路径，方便回到真值机做结构映射。

## 1. Dara + COD + BGMN

推荐 Linux、8--16 CPU、较大磁盘。GPU 对 BGMN 没有直接帮助。

```bash
python3 -m venv dara-env
dara-env/bin/pip install --upgrade pip
dara-env/bin/pip install dara-xrd==1.3.0 pandas pymatgen ray
```

Dara 自带 COD 2024 过滤索引，但实际 CIF 需要本地 COD mirror 或联网下载。大规模运行优先准备本地 mirror：

```bash
rsync -av --delete rsync://www.crystallography.net/cif/ COD_2024/
```

按 100 条样本的唯一元素集合建立并缓存候选集：

```bash
dara-env/bin/python fig4/benchmark/prototypes/prepare_cod_candidate_sets_v2.py \
  --cod-root /absolute/path/to/COD_2024
```

先跑 1 条冒烟测试，再全量续跑：

```bash
dara-env/bin/python fig4/benchmark/prototypes/run_dara_native_v2.py \
  --limit 1 --num-cpus 8

dara-env/bin/python fig4/benchmark/prototypes/run_dara_native_v2.py \
  --num-cpus 8 --resume
```

如果 BGMN 二进制与服务器 GLIBC 不兼容，按 Dara 官方安装文档配置 BGMN。环境失败应记录为 infrastructure failure，不计成算法给出错误物相。

## 2. CrystalShift + CrystalTree + COD front-end

CrystalShift 没有从元素查询数据库的原生层。本 benchmark 明确使用上一步冻结的 Dara-COD 候选集作为外接前端，结果名称必须写为 `CrystalShift + CrystalTree with COD front-end`。

安装 Julia 后建立隔离项目：

```bash
mkdir -p fig4/benchmark/method_envs/crystalshift
julia --project=fig4/benchmark/method_envs/crystalshift -e '
using Pkg
Pkg.add(url="https://github.com/MingChiangChang/CrystalShift.jl")
Pkg.add(url="https://github.com/MingChiangChang/CrystalTree.jl")
Pkg.add("JSON")
'
```

安装 CIF 转换用 Python 环境并克隆官方源码：

```bash
python3 -m venv crystalshift-python
crystalshift-python/bin/pip install numpy pandas scipy pymatgen xrayutilities
git clone https://github.com/MingChiangChang/CrystalShift.jl third_party/CrystalShift.jl
```

使用同一批 COD 候选建立 CrystalShift sticks，并预处理盲谱：

```bash
crystalshift-python/bin/python fig4/benchmark/prototypes/prepare_crystalshift_cod_v2.py \
  --converter third_party/CrystalShift.jl/src/cif_to_input_file.py
```

先冒烟测试，再全量：

```bash
julia --compiled-modules=no \
  --project=fig4/benchmark/method_envs/crystalshift \
  fig4/benchmark/prototypes/run_crystaltree_cod_v2.jl --limit 1

julia --compiled-modules=no \
  --project=fig4/benchmark/method_envs/crystalshift \
  fig4/benchmark/prototypes/run_crystaltree_cod_v2.jl --resume
```

该方法对候选相数近似线性、对最大共存相数呈指数依赖。若某些元素体系含大量 COD 候选，可能需要较长时间；不能看到真值后再按样本人工删候选。CrystalShift activation 只用于相内排序，不写入 `predicted_weight_fraction`。

## 3. XERUS

官方仓库：https://github.com/pedrobcst/Xerus ；论文版本建议固定到 v1.0r1。XERUS 依赖 MongoDB、GSAS-II 和在线材料数据库接口。旧仓库内嵌的 GSAS-II 二进制在新 macOS/ARM 或新 Python 上可能不兼容，因此新机器优先安装官方 GSAS2MAIN，再接入 XERUS 前端。

原生 v2 配置必须满足：

- 输入每条 `sample_elements`；
- 数据库提供者及版本/API 固定；
- 使用同一 GSAS-II reference profile；
- `n_runs=3` 或预注册的 `auto`，不可读取逐样本真实相数；
- 保存所有数据库 ID、最终组合、Rwp、weight fraction、失败和运行时间。

XERUS 的数据库/MongoDB 配置与机器相关，当前不把账号、API key 或本地缓存上传到仓库。

## 输出与回传

将以下结果目录提交回私有仓库：

```text
fig4/benchmark/results/atomly_core_v2/dara_cod_native/
fig4/benchmark/results/atomly_core_v2/crystaltree_cod_frontend/
```

不要提交：

```text
fig4/benchmark/datasets/atomly_core_v2/internal/
fig4/benchmark/datasets/atomly_core_v1/phase_pool/
```

