# LeaseDD · 本地多人尽调工作台

当前交付 **M0/M1 完整链路与 M2 财务资料提取**：浏览器登录 → 项目授权 → 原件上传 → Markdown 转换 → Agnes 文档分类、报表解释、逐行提取 → 本地来源与三表勾稽核验 → Decimal 指标 → 后台章节生成 → Word 待复核稿。

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

「主要财务指标」「财务分析」「财务附注」已接入上传报告，按参考平台的行名、顺序和单位展示。默认只显示筛选和表格，点击数值查看公式与来源。ROE、扣非指标和股份数量从摘要及附注读取；三表与补充披露共同用于 Decimal 计算。原三指标和人工事实导入保留在「更多操作」。铭普光磁对账范围、缺少的比较期及剩余口径见 [参考平台对账验收](docs/acceptance/reference-parity.md)；尚未实现完整指标、全部附注结构化、行情、同业库及汇率服务。

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
