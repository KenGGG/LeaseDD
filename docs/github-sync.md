# GitHub 同步

源码仓库：https://github.com/KenGGG/LeaseDD（公开）。

仓库包含应用源码、测试、合成夹具、原设计包、数据契约、部署文件和依赖锁文件。`.env`、真实企业资料、数据库、备份、浏览器会话及 `runtime/` 验收产物不随源码上传。验收文档中的 `runtime/` 路径指向部署服务器的本地记录，在 GitHub 上没有对应文件。

后续在项目目录查看变更后提交并同步：

```bash
git status --short
git diff
git add <本次需要提交的文件>
git diff --cached --stat
git commit -m "说明本次修改"
git push
```

GitHub 保存源码版本；数据库及业务文件仍按 [备份恢复说明](../deployment/backup-restore.md) 单独备份。不要用强制添加将忽略的凭据或运行数据放入提交。
