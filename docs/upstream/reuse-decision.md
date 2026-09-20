# 上游采用记录

四个项目仅作为原设计包记录的设计参考；本轮没有复制、移植、逐行翻译或运行其源码，也没有安装其 Skill。

| 项目 | 静态材料许可记录 | 本轮采用方式 |
|---|---|---|
| DocForge | 设计包记录完整 MIT 文本 | 章节化工作流参考；独立实现 |
| credit-spread-portal | 具体许可文本待核实 | 计算与写作分离思路参考；独立实现 |
| BidMaster-Pro | 设计包记录 AGPL-3.0 头部 | 闸门概念参考；独立实现 |
| OpenBidKit | 设计包记录 AGPL-3.0 头部 | 模板副本填充思路参考；独立实现 |

`upstream.lock.json` 的 commit 为 null，真实 commit 尚未核实；reviewed_blobs 仅转录原静态核查指纹，不冒充当前 checkout。未迁入源码，因此该缺口不阻止本轮自主实现。第三方运行依赖采用 uv.lock 和 frontend/package-lock.json 固定；没有分发字体或真实客户资料。
