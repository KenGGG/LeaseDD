# 企业预警通财务数据采集契约（Task 1）

## 结论

采用 Quantradar 的现有方式可以复用已登录的持久浏览器环境，并在页面上下文中取得结构化 JSON。企业搜索、主要财务指标、三张表、财务分析和财务附注均不需要从可视表格中逐格解析。

因此首版应采用 `direct_json / small`：只建设薄适配器，不建设网页镜像、通用爬虫平台、复杂批次状态机或独立投影数据库。本文件只描述真实接口，尚未修改 LeaseDD 产品代码。

## 浏览器与登录状态

- 复用 Quantradar 已有的持久浏览器启动方式；本次探测能够直接打开企业详情页，页面标题正常，六个财务入口均可见。
- 登录态只在页面上下文中使用；采集实现不应读取或记录认证信息。
- 当前证据证明接口可由页面上下文请求稳定取得；尚未证明脱离浏览器、使用普通 HTTP 客户端能够可靠重放。因此首版应继续在页面上下文调用接口。

## 企业搜索

正常首页搜索框会先打开搜索面板，再由可编辑输入框发起请求。

| 项目 | 实际形态 |
| --- | --- |
| 方法 | `GET` |
| 路径 | `/finchinaAPP/v1/finchina-search/v1/multipleSearch` |
| 参数 | `text`, `type`, `skip`, `pagesize`, `template`, `isRelationSearch` |
| 候选容器 | `data.list[]` |
| 候选身份字段 | `code`, `name`, `type`, `stock`, `symbol`, `market`, `status`, `socialCreditCode`, `url`, `jumpAddress` |
| 多候选 | 单次响应返回排序后的零到多个候选；探测请求实际返回多个候选 |

搜索结果未观察到一个名称就能直接、可靠表达“已上市且有财务数据”的布尔字段。最小实现应以候选的证券相关字段作上市判断，并在选中候选后以财务接口是否返回有效数据作为财务可用性判断，不能把登录或请求失败解释为“没有财务数据”。

## 财务数据导航树

六个一级栏目按页面顺序为：

1. 主要财务指标
2. 资产负债表
3. 利润表
4. 现金流量表
5. 财务分析
6. 财务附注

财务分析在本次探测公司中观察到 7 个下级栏目：

- 每股指标
- 盈利能力
- 偿债能力
- 营运能力
- 成长能力
- 现金流量
- 杜邦分析

财务附注在本次探测公司中观察到 19 个显示名称，对应 17 个独立数据模块：

- 审计报告
- 主营构成
- 主要销售客户
- 主要供应商
- 应收账款账龄分析
- 前五名应收账款
- 计提坏账的重大应收账款
- 预付款项账龄分析
- 账龄超过1年的重要预付款
- 前五名预付款
- 按款项性质分类
- 其他应收款账龄分析
- 前五名其他应收款
- 应付账款账龄分析
- 货币资金
- 存货
- 受限资产
- 财务费用
- 非经常性损益

其中“账龄超过1年的重要预付款”和“按款项性质分类”与父模块共享入口。生产适配器应保存页面返回的模块标识与父子关系，不把显示名称当唯一键，也不硬编码所有公司的附注树。

## 六类数据接口

| 栏目 | 方法与路径 | 期间 | 单位与值 | 下级加载 | 导出 | DOM 兜底 |
| --- | --- | --- | --- | --- | --- | --- |
| 主要财务指标 | `GET …/finance/report/getMainIndicators` | 一次响应包含多期 | `head/key/unit/level` 为平行字段数组，`value[期间][字段]` | 无 | 未观察到 | 不需要 |
| 资产负债表 | 同上，以 `childType/pageCode` 区分 | 一次响应包含多期 | 同上 | 无 | 未观察到 | 不需要 |
| 利润表 | 同上，以 `childType/pageCode` 区分 | 一次响应包含多期 | 同上 | 无 | 未观察到 | 不需要 |
| 现金流量表 | 同上，以 `childType/pageCode` 区分 | 一次响应包含多期 | 同上 | 无 | 未观察到 | 不需要 |
| 财务分析 | `POST …/finance/table/header-and-data`；筛选项来自 `POST …/finance/table/filter` | `dataList[]` 一次返回多期，每期含 `reportDate` | `fieldList[].unit/dbUnit`；字段定义与期间行分离 | 每个 `pageCode` 一次请求 | 未观察到 | 不需要 |
| 财务附注 | `GET …/finance/getCompanyF9Data` | `head` 与二维 `value` 一次返回多期 | 表头/行元数据携带展示含义，未观察到独立全局单位字段 | 每个 `child_type` 一次请求 | 未观察到 | 不需要 |

三表请求还带有 `auditYear`, `dataType`, `displayCurrency`, `mergeRange`, `reportDate`, `reportDateType`, `unitCode` 等明确参数。不能只保存格式化文本；应同时保存原字段、原值、期间、单位和请求口径。

### 脱敏响应结构

```text
getMainIndicators.data = {
  head: string[], key: string[], unit: string[], level: number[],
  blankNum: number[], formula: string[], value: scalar[][]
}

header-and-data.data = {
  fieldList: [{name, value, indent, unit, dbUnit, description, formula, children}],
  dataList: [{reportDate, <field-id>: scalar}], total: number
}

getCompanyF9Data.data = {
  leftTreeShow: boolean, head: array, value: scalar[][],
  color: scalar[][], link: scalar[][], level: number[]
}
```

空值必须保持空值；不得转为零。层级、缩进、公式、颜色和链接属于来源展示元数据，不应反向改变原值。

## 历史期间、分页和稳定性

- 代表请求均在一次响应中返回多个历史期间；未观察到滚动或分页才能补齐同一模块历史数据。
- 下级模块按 `pageCode` 或 `child_type` 分别加载，因此“全部财务分析/附注”需要枚举模块后逐模块请求，但不需要模拟逐行滚动。
- 栏目名称不是稳定主键；应保留接口模块标识、请求口径和原始字段名。
- 未观察到 Excel/CSV 下载接口，因此本轮不下载文件，也不把导出路径作为首版依赖。
- 页面前端可能调整路径、参数或字段，适配器应对必需字段做显式校验，并把结构变化标为导入错误。

## 最小 LeaseDD 适配器

建议只实现三个动作：

```text
search(name) -> candidates
enumerate(company) -> available modules
collect(company, module) -> original structured rows/cells
```

预计首版只需要：

- 3 个存储概念：项目企业绑定、一次导入记录、企业预警通原始财务数据；
- 2 个写操作：搜索/选择并导入、失败后重试；
- 1 个读取适配器：把三表数据转换为现有财务页面 view model；
- 页面上一个“从企业预警通导入”入口及来源/更新时间/不完整状态；
- 七条公式继续作为导入后的 warning，不阻断导入，不修改来源值；
- 企业预警通路径不调用 Agnes。

原九任务方案中可删除：项目创建时自动匹配、候选生命周期状态机、独立批次管理中心、StatementProjection/StatementItem 物化层、七个独立 provider API、版本对比与采集控制台。财务附注不应预置全公司通用目录，而应按每家公司实际模块枚举。

## 本轮边界

本结论只证明铭普光磁及当前网站版本的接口形态。尚未创建金银河、德方纳米、气派科技、昊志机电项目，尚未验证四家公司数据完整性，也尚未修改数据库、后端、任务队列或前端。下一阶段应先实现薄适配器，再以这四家公司验证结构差异。
