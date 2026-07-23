# XERUS 与 CrystalShift/CrystalTree 当前运行状态

## 范围

本记录只使用盲输入、候选 manifest、运行记录和方法输出，不读取私有真值，也不在 DGX 上计算
benchmark 准确率。

## CrystalShift 候选转换：最终完整

旧版本曾只有 5,591/6,622 条候选完成转换，因此旧诊断文字中的 84.4% 转换率已经失效。统一修复后：

- 冻结 COD 候选记录：6,622；
- 最终成功转换：6,622；
- 最终转换失败：0；
- 转换策略：5,734 条官方直接转换、870 条对称性标准化、18 条 P1 标准化；
- 结构验证失败：0；
- 实质结构改变：0；
- 原始 XRD 在转换前后 SHA-256 完全一致。

906 条失败的中间尝试仍保留在 attempt manifest 中，用于审计解析器兼容问题；它们不能再解释为
最终候选丢失。四条候选元素键与 CIF 实际元素不一致的记录也继续保留并报告，没有根据预测结果
手工删除。

## CrystalTree 100 条正式运行：完成

正式结果位于 `crystaltree_cod_frontend_v2/`：

- 100/100 个样品各有最新 `status=ok`；
- 全部使用 `maxiter=512` 和统一配置 `simple_fixed_sigma_0p1_maxiter512`；
- 100 个样品均保存 top-3 hypothesis，共 300 行；
- top-1 共输出 196 个预测相，196 个入选 CIF 全部存在且 SHA-256 通过；
- 累计单样品搜索时间 11,987.3 s，中位数 25.8 s，最大值 1,132.0 s；
- 单 writer 的 resumed full run wall time 为 3:13:15；
- 再次使用同一 `--resume --maxiter 512` 命令会跳过全部 100 条。

这是一套冻结的 README-prior baseline。CrystalShift activation 是模型内部量，不能解释为质量分数
或摩尔分数。准确率只允许在本地使用私有真值另行计算。

## XERUS 100 条正式运行：完成

正式结果位于 `xerus_native_pilot_v2/`；目录名沿用早期 pilot，但当前内容已经是冻结的 100 条全量结果：

- 100/100 个样品各有最新 `status=ok`；
- OQMD 仅使用校验后的冻结 OPTIMADE cache，正式日志没有实时 `oqmd.org` 请求；
- 100 个候选 manifest 共 46,947 条样品内唯一候选：COD 23,663、OQMD 18,440、
  MP 4,612、ODBX 232；
- 当前输出共 286 个预测相：2 个样品返回 1 相、10 个返回 2 相、88 个返回 3 相；
- 当前累计正式分析时间 7,018.0 s，中位数 44.0 s，最大值 376.8 s；
- 286 个入选 CIF 全部存在，输出内 SHA-256 和汇总校验文件均通过；
- 每个样品报告的 XERUS 质量分数之和为 1。

完整后台控制台输出保留为
`xerus_native_pilot_v2/logs/full_background_launcher.log.gz`。该文件由原始
12,634,157-byte 日志无损压缩得到；解压后 SHA-256 为
`6639afcc853c502fcaf6d709e3774ada5e0c40327ba12e7ef306f6eb07c6ccb9`。

首轮 21 个样品级错误保留在 append-only 审计中：20 个组合精修的
`no reflections in data range`，以及 1 个不参与最终结果的空诊断图错误。恢复补丁只把这一种
无反射组合赋予 XERUS 已有的无效拟合哨兵值，并跳过空诊断图；候选、`n_runs=3`、`n_jobs=4`、
仪器 profile、求解设置和全局最多三相均未改变。修复 smoke 通过后重跑失败样品，最终
latest-state gate 为 100/100。

## 当前状态

CrystalShift + CrystalTree 和 XERUS 的 Atomly-Core-100 盲测输出已经冻结。DGX 分支不得加入
私有真值或准确率。下一步是在本地用预注册 Atomly--COD 等价 ID 和 StructureMatcher 规则揭盲，
分别报告 unconditional、coverage-conditioned、相级和样品级指标。
