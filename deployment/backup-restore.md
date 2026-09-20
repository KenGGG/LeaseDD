# 本地备份与恢复

同时备份 PostgreSQL 和项目文件，单独备份其中一项不能恢复完整证据链。以下命令在部署目录执行，备份位置使用服务器受控目录，不提交 Git。以当前 Compose 环境为准；步骤会短暂暂停 API 和 worker。

## 备份

```bash
mkdir -p /tmp/leasedd-backup
chmod 700 /tmp/leasedd-backup
docker compose stop api worker
docker compose exec -T db pg_dump -U leasedd -d leasedd -Fc > /tmp/leasedd-backup/database.dump
docker compose run --rm --no-deps --user root --entrypoint tar api -C /data/files -czf - . > /tmp/leasedd-backup/project-files.tar.gz
sha256sum /tmp/leasedd-backup/database.dump /tmp/leasedd-backup/project-files.tar.gz > /tmp/leasedd-backup/SHA256SUMS
docker compose start api worker
```

另行安全备份部署版本、`.env` 和 Caddy 本地 CA 的存储卷，保留环境与证书。凭据与 CA 私钥不放在普通报告包中。备份失败时先确认文件完整性，再恢复服务；不要把空文件当有效备份。

## 恢复

在独立恢复环境先验证备份，采用匹配的应用版本及 schema。先只启动数据库，不执行 bootstrap；文件恢复到新建的空 project_files 卷，不覆盖正在使用的客户卷。

```bash
sha256sum -c /tmp/leasedd-backup/SHA256SUMS
docker compose up -d db
docker compose exec -T db pg_restore -U leasedd -d leasedd --clean --if-exists < /tmp/leasedd-backup/database.dump
docker compose run --rm --no-deps --user root --entrypoint tar api -C /data/files -xzf - < /tmp/leasedd-backup/project-files.tar.gz
docker compose run --rm --no-deps --user root --entrypoint chown api -R 10001:10001 /data/files
docker compose run --rm --no-deps api python -m leasedd.integrity
```

验证成功后启动 API 和 worker，抽查登录、项目成员、原件、事实来源和报告下载。API 启动需要数据库的历史 migration 版本与应用匹配。过期租约可由 worker 恢复；无数据库指针的临时或孤立文件不视为成功报告。

本轮提供程序与操作说明，尚未完成 M5 的完整灾难恢复验收。恢复验证发现摘要或 manifest 不一致时应停止发布并保留异常，不自动修改原件或摘要以通过校验。
