# LeaseDD 首轮 M0/M1 实施与交付清单

**目标：** 建立局域网多人 WebUI 合成完整链路，不开放正式发布。

**需求依据：** 用户确认的 WebUI 平台方案及 LeaseDD_Integration_Plan 的接口、验收和来源规则；用户要求覆盖原方案不建设 WebUI 的限制。

- [x] 锁定 Python 3.12、uv.lock、前端 package-lock.json；Docker API／worker、PostgreSQL、Caddy 入口；冻结迁移。
- [x] Pydantic 契约导出 Schema，保留静态上游核查边界和不移植代码决策。
- [x] 服务端账号与会话、同源／CSRF、管理员创建账号及项目、独立编制／审核成员绑定。
- [x] 原件受控上传、SHA256、只读存储、全部格式处理状态和文本行号定位。
- [x] 完整事实集导入、原文科目和值校验、版本冲突保护、理由和历史。
- [x] 三个 Decimal 指标、来源／范围／期间校验、缺失及零分母状态。
- [x] 独立 worker、项目串行任务、三次尝试、过期租约及响应、幂等导出认领、独立尝试产物。
- [x] 合成单章、Agnes OpenAI-compatible 适配、资料许可、Schema／数字引用／问题覆盖校验。
- [x] 章节编辑版本保护和不可变历史；从冻结合成 DOCX 模板副本导出真实财务表格。
- [x] 自动规则、权限、错误响应、恢复、真实 PostgreSQL 竞争及真实浏览器流程测试。
- [x] README、部署、备份／恢复与完整性检查、阶段验收、后续路线和文件指纹。

生产框架／模板、真实 Agnes 端点验证、完整多格式财务解析、风险工作流、正式人审发布和真实客户验收仍按 M2–M5 推进。测试运行详情以 docs/acceptance/test-results.json 为准，不从单个合成案例推断生产能力。
