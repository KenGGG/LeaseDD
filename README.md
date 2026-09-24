# LeaseDD · 本地多人尽调工作台

当前交付 **M0/M1 完整链路与 M2 财务资料提取**：浏览器登录 → 项目授权 → 上市公司企业预警通结构化导入或非上市公司原件识别 → 本地来源与三表勾稽核验 → Decimal 指标 → 后台章节生成 → Word 待复核稿。

支持编制／审核账号分离，项目正文、任务和下载均要求成员权限。审核人员首轮只读；定稿发布明确禁用。当前只有合成框架和模板，不是可直接用于生产的完整尽调系统。

## 局域网部署

需要 Docker 与 Docker Compose。

1. `cp .env.example .env` 后执行 `chmod 600 .env`，设置数据库和初始管理员密码（至少 12 个字符）。数据库密码使用 URL-safe 字符；可用 `python3 -c 'import secrets; print(secrets.token_hex(24))'` 生成。
2. 设置 `LEASEDD_HOST` 为客户端可解析的服务器域名或 IP，`LEASEDD_BIND_IP` 为服务器局域网 IP。默认仅绑定 `127.0.0.1`。
3. `docker compose up -d --build`。migration 与 bootstrap 成功后启动 API 和 worker。
4. 访问 `http://<LEASEDD_HOST>:<LEASEDD_PORT>`。当前局域网配置使用 HTTP 和独立端口，不占用 80 端口；当前服务器地址为 `http://172.30.10.150:5173`。
5. 管理员登录「账号与服务配置」，创建编制、审核账号及项目。管理员不会自动获得项目正文权限。

只有 Web 入口端口对局域网开放；数据库、API、worker 和原件目录不直接开放。`.env` 和真实项目资料不提交 Git。

## Agnes 配置

在服务器 `.env` 中填写 `AGNES_API_KEY`，更新后执行 `docker compose up -d --force-recreate api worker`。管理员网页配置兼容 OpenAI 的 base URL（例如服务实际提供的 `/v1` 根路径）与模型名称；后台调用 `<base_url>/chat/completions`。

资料上传后先处于“等待识别”状态，不会自动调用 MinerU、MarkItDown 或 Agnes。资料齐全后，在“资料与证据”页勾选文件并点击“批量识别”。勾选“使用 Agnes 识别财务语义”即授权所选材料发送 Agnes：先分类文档中的表格，再解释主报表的主体、口径、单位及列期间，最后逐行提取；本地规则仅作为第二意见。不勾选时只运行本地转换和原有本地解析，不向 Agnes 发送材料。授权取决于实际服务部署位置；本地 WebUI 不代表模型推理在本地。

Agnes `agnes-2.5-flash` 的真实端点已经用合成三表验证。适配器关闭 Thinking，要求 JSON 响应；共享限流默认每分钟18次，上限20次，重试也占额度。每个阶段最多发送3次，成功响应保存摘要检查点；同一任务恢复时可复用。512K上下文与65K输出按保守字节预算控制，优先完整逻辑表，必要时按行拆分并保留表头及原坐标。

错误 JSON、越界定位、错误期间、无证据单位及原文数值冲突不会成为已核验数据。未知科目保留原名、原值和定位，标为未匹配，不补零、不丢弃。`VERIFIED` 只表示程序核验，不等于人工审核。重识别已完成资料需显式勾选“重新识别已完成资料”；新批次保留旧记录，不自动重跑历史材料。详细测试与尚未通过的跨企业验收见 [本次识别升级记录](docs/acceptance/agnes-semantic-2026-09-20.md)。

PDF 和图片使用 MinerU，DOCX/XLSX/PPTX 使用 MarkItDown，TXT/MD/CSV 直接转换。worker 通过 `MINERU_URL` 访问现有 MinerU 服务；默认 Docker 地址为 `http://host.docker.internal:58000`。

## 上市公司财务数据

管理员可以在项目财务页手动选择企业，从已登录的企业预警通浏览器环境导入结构化财务数据。项目创建流程不依赖企业预警通；企业绑定、一次导入记录和模块级原始财务数据分别保存，旧批次不会被新批次覆盖。

当前采集目录为 40 个模块：主要财务指标、三张财务报表、财务分析 7 项，以及财务附注 29 项（含原站禁用项）。每个模块保留原始 JSON、来源接口、请求参数、期间、单位、口径和响应摘要；空值保持为空，不补零。三张表转换为现有财务 API 和页面结构，七条恒等式只产生质量提示，不修改或阻断来源值。企业预警通导入路径不调用 Agnes，也不会与 PDF 提取结果逐格拼接。40 项记录包含原站禁用栏目，不能全部计为有数据。
主要财务指标和财务分析按来源期间矩阵、指标层级及单位展示；财务附注根据来源结构展示期间矩阵或明细子表。历史批次中未写入解析层的分析子级值可从同批已保存的原始响应还原，无需重新导入。

2026-09-24 四家公司均完成新版 40 项导入：金银河 31 项有数据 / 9 项原站禁用，德方纳米 30/10，气派科技 29/11，昊志机电 32/8；关键三表可用，导入路径未调用 Agnes。两家公司经历一次定向重试；不能把 40 项记录等同 40 项有数据。详细核验、耗时和限制见 [四家公司验收记录](docs/acceptance/enterprise-warning-four-companies.md)，最新批次的[只读核对结果](docs/acceptance/enterprise-warning-four-companies-current.json)按 40 项目录区分有数据、原站禁用、失败和缺失。该结果只证明这四家公司及当前企业预警通页面版本，不代表任意企业或未来页面结构均可兼容。

当前部署通过本机专用浏览器服务的受限 Unix socket 连接已登录的企业预警通，Docker worker 不挂载浏览器配置。不要把浏览器用户目录、Cookie、密码或认证响应提交到 Git，也不要将个人持久浏览器配置直接挂载到容器。管理员导入仍须具备项目写入授权；本轮四家公司临时授权在验收后已撤销，不改变原编制/复核成员。

登录恢复：采集器遇到“我已知晓”异地登录提示会关闭提示并继续；若出现登录页，仅尝试一次已有登录表单，不提取或猜测密码。仍停留在登录页时返回 `authentication_required`，不视为无财务数据；扫码、验证码等需在浏览器中完成。登录请求和响应不作为财务来源保存。本机专用浏览器服务已部署，API/worker 通过受限 Unix socket 调用；六类财务栏目的完整交互对照仍未完成。

批次内若认证、浏览器启动或配置缺失导致采集受阻，会停止剩余模块请求并保留已成功数据，避免对全部模块重复登录。浏览器启动失败单独记录为 `browser_unavailable`；可仅重试失败模块。此前客户端浏览器工具故障的复现与边界见[浏览器排障记录](docs/acceptance/browser-runtime-blocker.md)，不等于当前专用服务不可用。

Quantradar 实现核对：其应用采集器直接使用 Python Playwright 与 Chrome 持久化配置，不依赖客户端浏览器扩展。LeaseDD 已补上同样的用户名框 ArrowDown/Enter 自动填充触发步骤，再检查提交按钮可用性。客户端浏览器插件故障与应用采集器可运行性需分别验证。

六栏目增量进展（2026-09-24，**生产导入已完成，完整界面复制尚未验收**）：四家公司新版批次各有 40 项来源记录，29 个附注目录名称与四家公司原站目录逐项一致；禁用项单列，不伪造财务响应。三表、主要指标、财务分析及财务附注都已在德方纳米生产页实际打开，币种/汇率切换及指标、审计报告 Excel 下载可用。三表投影累计 143,421 个单元格与已保存的来源行列、原值和响应摘要一致；这属于数据库一致性检查，不等于逐格人工对照原站页面。德方纳米另有 3 条早期母公司资产负债表勾稽报警，来源值不因此修改。

最新自动回归：后端 339 通过 / 3 跳过，前端 55 通过，生产构建及受控浏览器筛选/Excel 烟测成功。主要指标与三表各保存 18 组币种/汇率响应；现有 data 接口按栏目加载并校验批次与摘要。3Y/5Y/10Y 使用滚动报告期窗口，Excel 列数与页面同步；主要指标和三表趋势弹窗已接入，三表趋势只使用保存的披露列，导出复用现有 data 接口。两项前五名应收款记录表已确认原站旧接口返回精确万元数值，采集器现直接取得原始十进制值并支持报告期、年度、排序、单位及精度；旧生产批次仍是 F9 压缩摘要，页面已标识“非原站精确表”，须经现有任务流程重导入后才可用精确值。科学计数法金额在来源核验、网页及 Excel 中按 Decimal/精确十进制处理，原文不改。仍待逐项完成全部专项附注交互/导出、财务分析趋势、不同口径工具栏组合和视觉细节的原站对照；当前耗时没有同企业 PDF + Agnes 对照基线，不能声称已证明加速。持续目标与证据见[六栏目对照记录](docs/acceptance/enterprise-financial-ui-parity.md)和[增量计划](docs/superpowers/plans/2026-09-23-enterprise-financial-parity.md)。

## 本机开发

```bash
UV_CACHE_DIR=/tmp/leasedd-uv uv sync --frozen
npm ci --prefix frontend
mkdir -p runtime
export LEASEDD_DATABASE_URL=sqlite:///runtime/dev.sqlite
export LEASEDD_DATA_DIR=runtime/dev-files
export LEASEDD_SECURE_COOKIE=false
export LEASEDD_PUBLIC_ORIGIN=http://127.0.0.1:5173
.venv/bin/alembic upgrade head
export LEASEDD_ADMIN_USER=admin
read -rs -p '管理员密码: ' LEASEDD_ADMIN_PASSWORD
export LEASEDD_ADMIN_PASSWORD
.venv/bin/python -m leasedd.cli bootstrap
unset LEASEDD_ADMIN_PASSWORD
.venv/bin/uvicorn leasedd.server:app --host 127.0.0.1 --port 8000 --no-access-log
```

另外两个终端使用相同数据库和文件目录环境变量，分别启动：

```bash
.venv/bin/python -m leasedd.worker
npm run dev --prefix frontend
```

开发代理入口为 `http://127.0.0.1:5173`。SQLite 仅作本机开发／测试；多人部署使用 PostgreSQL。不要在 HTTP 局域网部署中关闭 Secure Cookie。

## 验证合成样例

1. 创建两个不同账号和一个项目，以编制账号登录。
2. 上传 `fixtures/synthetic_statement.txt`，点击「批量识别」，完成后点击「查看原文」。
3. 复制页面文档 ID 到 `fixtures/synthetic_facts.json` 的 `document_id`，将另存副本导入「财务核对 → 主要财务指标 → 更多操作」。网页使用当前载入的项目 revision 提交；陈旧页面会得到版本冲突。
4. 点击「计算当前事实」：资产负债率 80.00%，有息负债率 30.00%，存货缺失导致速动比率为空并有原因。
5. 点击「生成测试章节」，等待后台任务完成。
6. 在「复核与导出」生成 Word 并下载。文件含测试标识、固定标题、真实表格与来源对照。

事实导入首轮限 UTF-8 文本行 `concept: value`。JSON 包含 document_id、sha256、expected_revision、reason 和 facts；每项包含 concept、value、entity、scope、period、currency、unit、line、quote。每次导入替换当前**完整事实选择集**，旧集保留历史；空值不补零。直接 API 调用必须提供正确 expected_revision，不能用旧文件覆盖当前选择。

## 测试与交付记录

财务展示已改为报表矩阵：在「财务核对」左侧选择资产负债表、利润表或现金流量表，科目按行、报告期按列。可按主体／报表口径／币种、报告期和年度筛选，切换金额单位、排序、隐藏空行及搜索科目。点击数字可查看原件、原值、Markdown 行号和核对意见；同口径同科目不同值显示冲突，缺失值不补零。CSV 导出包含当前视图及候选来源对照，可用 Excel／WPS 打开。

「主要财务指标」「财务分析」「财务附注」可以读取上传报告，也可以展示企业预警通导入的原始栏目层级。默认只显示筛选和表格，点击数值查看公式与来源。ROE、扣非指标和股份数量从摘要及附注读取；三表与补充披露共同用于 Decimal 计算。原三指标和人工事实导入保留在「更多操作」。铭普光磁 PDF 对账范围、缺少的比较期及剩余口径见 [参考平台对账验收](docs/acceptance/reference-parity.md)；企业预警通四家公司结构化导入结果见 [企业预警通验收](docs/acceptance/enterprise-warning-four-companies.md)。尚未实现行情、同业库及汇率服务。

```bash
.venv/bin/python -m pytest -q
npm test --prefix frontend
npm run build --prefix frontend
.venv/bin/python -m leasedd.cli schema
```

真实 PostgreSQL 验证使用专门测试数据库：

```bash
LEASEDD_TEST_DATABASE_URL='postgresql+psycopg://<user>:<password>@127.0.0.1:<port>/<test_db>' .venv/bin/python -m pytest -q
```

测试创建并删除独立随机 schema。不要指向客户数据库。浏览器脚本 `tests/browser_acceptance.py` 需要隔离的本机 API、worker、Vite 和 Playwright Chromium；通过 LEASEDD_BROWSER_URL、LEASEDD_BROWSER_ADMIN、LEASEDD_BROWSER_PASSWORD 配置测试环境，运行结果写入 runtime/acceptance。

阶段验收见 [docs/acceptance/M0-M1.md](docs/acceptance/M0-M1.md)，后续路线见 [docs/development-roadmap.md](docs/development-roadmap.md)，备份恢复见 [deployment/backup-restore.md](deployment/backup-restore.md)。原设计包保持完整；上游引用、未验证 commit 与许可边界见 docs/upstream。
