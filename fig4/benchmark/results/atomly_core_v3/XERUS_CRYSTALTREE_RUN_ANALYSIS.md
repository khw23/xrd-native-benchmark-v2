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

## XERUS 完整候选 pilot：通过

`XRDV3_0046` 使用 7 个元素子体系的冻结 OQMD OPTIMADE cache：

- OQMD 原始记录：150；
- XERUS 原生候选快照：226，其中 OQMD 149、COD 61、MP 12、ODBX 4；
- 候选准备时间：95.3 s；
- 进入 XERUS 模拟/筛选的候选：63；
- 正式分析时间：27.4 s；
- 最终 Rwp：7.0242%；
- 返回 AgCl 与 AgBr 两相、数据库 ID、CIF 和 XERUS 质量分数；
- OQMD 全部来自冻结 cache，正式日志没有实时 `oqmd.org` 请求。

该样品证明离线 OQMD 路径、MongoDB、GSAS-II、CIF validator 和正式 refinement 可以端到端运行。
它不能单独证明 100 条的运行时间；XERUS 的耗时仍随候选模拟和组合精修规模变化。

## 下一步：不再做三档 smoke

用户已批准跳过额外三档 smoke。下一步固定为：

1. 在本机下载并校验 Atomly-Core-100 所需的 470 个唯一 OQMD 元素子体系；
2. 将完整 cache 传到 DGX 的
   `fig4/benchmark/method_inputs/oqmd_optimade_cache_v3_full/`；
3. 在固定 MongoDB 中对 100 条执行一次 `prepare-candidates-only`；
4. 候选准备无错误后，使用同一 cache/MongoDB/profile 直接执行 100 条正式 XERUS；
5. 整个流程由 `run_xerus_full_background_v3.sh` 作为一个 `nohup` 后台任务运行；DGX Codex 只检查
   启动状态和初始日志，然后退出，不持续轮询。

完整 cache、MongoDB、环境和所有候选 CIF 不提交 GitHub。只提交候选 manifest、预测、最终入选 CIF、
校验和、环境记录及必要日志。私有真值不得上传 DGX。
