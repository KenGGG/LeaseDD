# WebUI 统一样式与数据可读性验收

日期：2026-09-20。已部署至现有 HTTP 5173 入口，仅更新 web 服务。

## 调整范围

- 全站统一深色正文、清晰的辅助文字、蓝色操作按钮，以及导航、表单、面板和边框样式。
- 中文使用系统无衬线字体栈，包含 Linux 的 Noto Sans CJK SC；无需下载外部字体。
- 财务数值由 12px 提升至 15px，使用 Arial / Noto Sans 数字字体及 tabular-nums；主体科目保持 14px，数值行高至少 43px。
- 加深表头、行列边界和隔行背景；保留固定表头、固定科目列以及横向滚动。
- 登录、项目列表、项目概览、资料、章节、导出、管理及财务页面共用文字和边框变量。
- 手机资料状态自动换行；侧栏在矮屏可滚动；表格和折叠区的键盘焦点可见。

## 验证

- `npm run build --prefix frontend`：TypeScript 与 Vite 构建通过。
- `npm test --prefix frontend`：11 项通过。
- `tests/ui_readability_browser.py`：7 个非财务页面 × 1600 / 1024 / 390px 宽度通过。使用合成只读 API，检查页面溢出、资料状态截断、主要文字尺寸及登录键盘导航。
- `tests/financial_reference_browser.py`：已部署前端的铭普光磁表格、指标计算来源、附注与手机布局通过。接口采用之前从上传 PDF 核对得到的本地只读数据快照。
- `tests/financial_browser_acceptance.py` 与 `tests/financial_insights_browser.py`：预览构建回归通过，覆盖三表、筛选、单位精度、冲突、来源、模拟确认、CSV 以及指标/分析/附注交互。
- 实际渲染抽样：财务数字 15px，前景 RGB(29,41,57)、背景 RGB(247,249,252)，对比度 13.94:1。此结果为抽样，不代表全站逐元素可访问性审计。
- 部署后 HTTP 页面引用 `index-iCrECY9O.css`；全站样式检查和参考财务检查均重新通过。浏览器检查未修改真实项目数据。

截图及结果：`runtime/acceptance/ui-readability/`、`runtime/acceptance/reference-parity/`。

本次仅修改展示样式，未变更财务提取、计算或既有数据一致性结论。
