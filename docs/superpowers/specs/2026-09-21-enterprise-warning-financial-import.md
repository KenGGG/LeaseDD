# LeaseDD 企业预警通最小财务导入设计

日期：2026-09-21

## 1. 目标

管理员在现有项目财务页手动选择企业，并通过当前已登录的企业预警通浏览器环境导入结构化财务数据。首轮覆盖企业预警通当前可见的 17 个模块：

- 主要财务指标、资产负债表、利润表、现金流量表；
- 财务分析 7 项：每股指标、盈利能力、偿债能力、营运能力、成长能力、现金流量、杜邦分析；
- 财务附注 6 项：审计报告、主营构成、主要销售客户、主要供应商、货币资金、存货。

成功标准是金银河、德方纳米、气派科技、昊志机电四家公司不调用 Agnes，能够完整导入当前账号可访问的上述模块和历史期间，保留原值、空值、单位、顺序及来源，并且采集耗时明显低于上市公司 PDF + Agnes 路径。

## 2. 固定边界

- 项目创建流程不改，不自动搜索、匹配或导入企业。
- 不迁移现有铭普光磁项目。
- 企业预警通与 PDF 财务数据不自动逐格混合。
- 不建设自动匹配、候选生命周期、批次管理中心、版本对比、采集控制台或定时同步。
- 不增加逐单元格持久化、StatementProjection、StatementItem 或其他投影实体。
- 不归档完整网页，不记录密码、认证信息或与财务来源无关的页面内容。
- 企业预警通路径不调用 Agnes。

## 3. 已验证接口

采集复用 Quantradar 的持久 Playwright 浏览器方式，在页面上下文内调用当前网站接口：

| 数据 | 方法与路径 |
| --- | --- |
| 企业搜索 | `GET /finchinaAPP/v1/finchina-search/v1/multipleSearch` |
| 主要财务指标 | `GET /finchinaAPP/v1/finchina-finance/v1/finance/report/getMainIndicators` |
| 三张表 | `GET /finchinaAPP/v1/finchina-finance/v1/finance/report/getThreeReports` |
| 财务分析筛选 | `POST /finchinaAPP/v1/finchina-finance/v1/finance/table/filter` |
| 财务分析数据 | `POST /finchinaAPP/v1/finchina-finance/v1/finance/table/header-and-data` |
| 财务附注 | `GET /finchinaAPP/v1/finchina-finance/v1/finance/getCompanyF9Data` |

详细字段结构与探测限制以 `docs/acceptance/qyyjt-acquisition-contract.md` 和 `docs/acceptance/qyyjt-acquisition-summary.json` 为准。采集器不得依赖财务表格 DOM；页面交互只用于维持登录上下文和取得模块参数。

## 4. 最小采集器

采集器只提供三个业务动作：

```python
search(name: str) -> list[EnterpriseCandidate]
enumerate_modules(company_code: str) -> list[EnterpriseModule]
collect_module(company_code: str, module: EnterpriseModule) -> CollectedModule
```

要求：

- `search()` 返回企业代码、规范名称和可用的证券身份字段；多个候选不得默认选择第一项。
- `enumerate_modules()` 从当前页面取得实际模块树，不把旧快照或硬编码目录当作完成依据。
- `collect_module()` 保存原始 JSON、接口路径、请求口径、响应哈希、采集时间和最小解析结果。
- 登录失效、结构变化和空数据必须区分；异常不能解释成“非上市公司”或“没有财务数据”。
- 网站结构与已验证契约不一致时停止相应模块，返回明确错误，不用 DOM 猜值。

## 5. 三个数据实体

### 5.1 `EnterpriseBinding`

每个项目最多一条绑定，保存项目 ID、企业代码、规范名称、可用的证券身份信息、创建人和创建时间。重新选择企业只允许管理员显式操作；首版不实现自动匹配历史和候选状态机。

### 5.2 `EnterpriseImport`

一次导入对应一条记录，保存 ID、项目 ID、任务 ID、采集状态、质量状态、模块成功/失败清单、错误代码、开始与完成时间和总内容哈希。

采集状态只有 `queued | running | completed | partial | failed`，质量状态只有 `not_checked | passed | warning`。同一项目同一时刻只允许一个活动导入；重复提交返回现有活动任务。每次人工更新创建新记录，首版不建设批次管理 UI。

### 5.3 `EnterpriseFinancialData`

每个导入、每个模块保存一条数据：导入 ID、分类、模块键、模块名称和顺序，接口路径和脱敏请求口径，原始 JSON、响应哈希、采集时间，解析后的期间、单位、层级、表头和行列结构 JSON，以及模块状态和错误代码。

不拆成逐单元格记录。原始 JSON 不被映射、公式或界面修改。

## 6. 任务与完整性

复用现有 `Task` 和 worker，仅增加 `kind="enterprise_import"`、`mode="qyyjt"`。

1. 管理员搜索并选择企业，系统写入或更新绑定。
2. 导入接口创建 `EnterpriseImport` 和现有 `Task`。
3. worker 动态枚举模块并逐模块采集。
4. 每个成功模块立即保存；失败模块记录错误但不删除成功数据。
5. 17 个当前规定模块全部成功才是 `completed`，否则是 `partial` 或 `failed`。

登录失效、结构变化、网络错误和空模块分别使用稳定错误码。重试接口只重试当前导入中的失败模块；若没有可重试失败项则返回当前状态。

## 7. 财务读取与校验

三张表读取时由适配器转换为现有 `/financial-statements` 返回结构：

- 不创建或伪造 `Document`、`DocumentConversion`、`ExtractionRun`；
- 不写入现有 `FinancialStatement` 或 `FinancialItem` 表；
- 企业预警通绑定存在可读导入时返回企业预警通 statement view，PDF 当前值不得自动混入；
- `document_id`、`conversion_id` 等仅属于 PDF 来源的字段在企业预警通视图中为 `null`，前端按来源类型显示接口证据。

三张表只对明确映射的少量标准科目设置 `concept`。未知或歧义科目保留原名，不进入公式。

七条恒等式复用 `evaluate_statement_checks()`。企业预警通原值只有在来源模块成功、期间/单位明确、概念映射明确且数值可用 `Decimal` 解析时才能作为公式输入。公式结果只产生 `passed`、`warning` 或“缺少披露项，未检查”；不得改值、补零或阻断导入完成状态。

## 8. 四个 API

### `GET /api/projects/{pid}/enterprise`

返回当前绑定、活动任务、最近导入、17 个模块覆盖、失败模块、来源和更新时间。项目成员可读。

### `POST /api/projects/{pid}/enterprise/import`

仅管理员可调用。请求可包含 `query`；未绑定时返回候选列表，管理员带候选企业代码再次提交后绑定并入队。已绑定时直接创建人工更新任务。重复提交返回活动任务。

### `POST /api/projects/{pid}/enterprise/retry`

仅管理员可调用。重试最近一次 `partial` 或 `failed` 导入的失败模块，复用该导入记录和现有任务机制。

### `GET /api/projects/{pid}/enterprise/data`

项目成员可读。使用 `category` 和可选 `module_key` 查询原始栏目树或模块数据。三张表仍通过现有 `/financial-statements` 接口读取。

不新增候选确认、批次列表、批次详情、树或 statement 专用接口。

## 9. 最小界面

现有财务页增加来源、绑定企业、最近更新时间和完成状态；管理员可“从企业预警通导入”和“重试失败模块”，并可从搜索候选中选择企业。页面展示 17 个模块覆盖及失败模块简表。

三张表继续使用现有表格和公式诊断。主要财务指标、财务分析、财务附注使用现有财务工作区中的指标、分析、附注页签，改为读取企业预警通原始层级。首版不增加独立管理页面。

## 10. 权限与审计

- 只有管理员能搜索、绑定、导入和重试。
- 项目成员可以读取项目绑定和已保存财务数据。
- 搜索不写审计；绑定、导入开始、完成、部分失败、失败和重试写入现有 `Audit`。
- API 不返回原始认证信息、浏览器配置或完整请求头。

## 11. 测试与验收

自动测试至少覆盖：

- 搜索单候选、多候选、显式选择和不自动选首项；
- 登录失效、结构变化、空数据和单模块失败；
- 17 个模块完整性、`partial` 状态和失败模块重试；
- 原始 JSON 按模块保存且空值不变零；
- 三张表 view 转换、未知科目保留、单位与期间不串列；
- 七条公式只报警、不修改原值、不改变采集状态；
- 企业预警通项目不自动混入 PDF statements；
- 管理员写权限、成员读权限、重复提交幂等和审计记录；
- `enterprise_import` 路径的 Agnes 调用次数为零。

真实验收只创建或复用金银河、德方纳米、气派科技、昊志机电四个项目，主协办人员与铭普光磁一致。同名项目不得重复创建。每家公司记录企业代码、17 个模块覆盖、期间数、代表数字和空值保真、公式状态、总耗时，以及与现有 PDF + Agnes 耗时的可比结果。

## 12. 交付

- 可运行的薄适配器、3 个实体迁移、worker 任务、4 个 API 和最小财务页入口；
- 四家公司真实导入结果；
- 自动测试结果、耗时对比和剩余问题清单。

样本通过只说明四家公司及当前企业预警通版本的表现，不宣称兼容任意公司或未来页面结构。
