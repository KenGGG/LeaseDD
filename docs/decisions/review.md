# 独立代码复核处理记录

通过 requesting-code-review 工作流进行了两轮只读独立复核。

| 发现 | 处理与验证 |
|---|---|
| 数值子串被接受、科目不匹配 | 严格匹配原文科目和值；wrong value/concept 回归 |
| 事实导入缺少版本保护 | 必填 expected_revision，项目行锁与历史保留；陈旧版本拒绝 |
| worker 锁顺序反转 | 统一 project→task，认领使用 skip_locked；真实 PostgreSQL 竞争回归 |
| 过期 worker 覆盖有效导出 | 每 lease token 独立文件目录，发布前验证当前所有权 |
| worker 失败处理的所有权竞争 | 按 task ID、lease token 与 running 状态进行单条条件 UPDATE；旧所有者不能重置新尝试 |
| 前端跨项目／登录保留数据 | 会话 epoch、当前项目标识与异步响应 fencing；切换清空数据，页面仅渲染匹配项目 |
| 编辑时使用新版本提交旧草稿 | 编辑开始冻结基准版本，冲突时保留草稿并提示重新载入 |
| 合成标识和答复状态不一致 | 必须 synthetic=true；问题绑定对应指标，缺失指标不得标 answered |
| 初次并发登录限流插入竞争 | 数据库原子 upsert 初始化并锁定行；五次并发失败无500，第六次限流 |

部署复核确认依赖顺序、模板打包和阶段边界；实际构建、PostgreSQL 与 HTTPS 浏览器测试另行记录。未将代码复核等同于完整安全审计。
