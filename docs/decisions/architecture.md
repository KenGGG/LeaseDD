# LeaseDD M0/M1 架构决策

用户最新要求覆盖原设计包「不建设 WebUI」：采用局域网多人 React/TypeScript 工作台、FastAPI、PostgreSQL、独立 worker、本地文件及 Caddy HTTPS 入口。

领域计算与校验不依赖前端或模型。金额以十进制字符串存储，Decimal 计算与显示，前端使用服务器显示值。Pydantic 模型为 Schema 唯一来源；`python -m leasedd.cli schema` 重新导出。模板及公式在本轮固定为 synthetic-v1。

所有项目正文接口要求成员身份。平台管理员仅管理账号、服务和项目绑定，不自动获得所有项目正文权限。项目当前绑定一个编制人员和一个不同账号的审核人员。首轮审核人员只读，所有角色都不能发布定稿。完整的提交、退回、确认和定稿流程属于 M4。

会话令牌仅保存在 HttpOnly Cookie，服务器存摘要、CSRF token 和 8 小时有效期；生产入口启用 Secure Cookie、同源检查。API Key 从服务端环境注入，网页只配置 Agnes 地址和模型，HTTP 请求禁止重定向。授权资料按锁定事实构造最小任务包，不发送整个原件。

每个事实导入是完整候选选择集，必须带 expected_revision 和处理理由；旧版本追加保存，不能静默覆盖。首轮不做自动财报解析或跨文件候选合并。TXT 事实行必须符合 `concept: value`，只验证原文定位、科目和值；主体、范围、期间、单位由人工核对输入，不宣称材料真实性自动认证。重复科目维持 conflicted，不自动择优。

后台队列使用 PostgreSQL；认领与完成统一按 project → task 锁顺序。每项目最多一个活动任务，租约 180 秒，模型超时 60 秒，最多三次尝试。每次导出使用独立 lease token 目录；只有当前租约且输入仍有效的任务可登记下载记录。写完 DOCX 和 manifest 后才提交数据库指针。未登记产物属于未发布文件；自动清理和灾难恢复全面验收属于 M5。

运行清单统一命名 RunManifest，文件名 artifact_manifest.json。SQLite 仅用于离线测试和本机开发；多人部署使用 PostgreSQL，不声称 SQLite 模式支持多 worker 的生产并发。

生产框架与模板未提供，production_template_status=missing。包含的 DOCX 为自行生成的合成模板，不是原框架。原件文件权限防止普通误写，但 API 与 worker 同一操作系统身份不构成对恶意 Agent 的强安全隔离。
