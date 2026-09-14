# RAG 学术知识引擎 · 服务器部署指南

本指南面向"一台全新的云服务器"，从零到 HTTPS 正式对外，全部命令可复制执行。全程约 30–40 分钟（备案另计）。

```
用户 ──HTTPS──▶ nginx :443 ─┬─ /          → 前端静态文件（已构建进镜像）
                            └─ /api/      → backend:8000（SSE 流式无缓冲）
                                             ├─▶ mysql:3306（数据卷，仅容器网络可达）
                                             ├─▶ /app/data（chroma 向量库 + uploads 持久卷）
                                             └─▶ 出站：api.siliconflow.cn（模型调用）
```

**目录**

- [0. 速查（老手版）](#0-速查老手版)
- [1. 选服务器与域名](#1-选服务器与域名)
- [2. 服务器初始化](#2-服务器初始化)
- [3. 拉代码与配置](#3-拉代码与配置)
- [4. 启动与验证](#4-启动与验证)
- [5. 配置模型服务](#5-配置模型服务)
- [6. 域名与 HTTPS](#6-域名与-https)
- [7. 备份与恢复](#7-备份与恢复)
- [8. 版本更新与回滚](#8-版本更新与回滚)
- [9. 安全加固清单](#9-安全加固清单)
- [10. 故障排查](#10-故障排查)
- [11. 监控与用量](#11-监控与用量)
- [12. 卸载](#12-卸载)

---

## 0. 速查（老手版）

```bash
git clone https://github.com/gy288666/RAG3.git && cd RAG3/project/deploy
cp .env.production.example .env.production   # 填齐 4 个 change-me，生成 2 个 32 位 hex
docker compose up -d --build
curl http://127.0.0.1/api/health             # {"code":200,...} 即成功
docker compose run --rm certbot certonly --webroot -w /var/www/certbot -d 你的域名 --email 邮箱 --agree-tos
docker compose exec nginx nginx -s reload
```

新手请从头按顺序执行，每一步都附有预期输出。

## 1. 选服务器与域名

| 项 | 建议 | 说明 |
|---|---|---|
| 配置 | 2 核 2G 起，系统盘 40G+ | MySQL + Chroma + 前端构建峰值约占 1.5G 内存；文档量大时向量库占磁盘 |
| 系统 | Ubuntu 22.04 / 24.04 | 本指南命令按 Debian 系编写 |
| 地域 | 国内（需 ICP 备案，约 2–4 周）或香港/海外（即买即用） | 面向国内用户选国内节点延迟低；出站调用 SiliconFlow 不受备案影响 |
| 带宽 | 3M 固定带宽或按流量 | 页面静态资源经 gzip 后 <300KB，SSE 是长连接低流量 |
| 域名 | 任意注册商，A 记录 → 服务器 IP | Let's Encrypt 免费证书，90 天自动续期（见第 6 节） |

安全组/防火墙放行：**80、443**（TCP）；22 端口建议限定来源 IP。

## 2. 服务器初始化

### 2.1 登录并装 Docker

```bash
ssh root@<服务器IP>
curl -fsSL https://get.docker.com | sh
docker --version          # 预期: Docker version 27.x 或更高
docker compose version    # 预期: Docker Compose version v2.x
```

### 2.2 建立部署用户（不用 root 跑服务）

```bash
adduser --disabled-password deploy
usermod -aG docker deploy
mkdir -p /home/deploy/backup && chown deploy:deploy /home/deploy/backup
```

### 2.3 SSH 加固（建议立即做）

```bash
# 在你自己的电脑上：ssh-copy-id deploy@<服务器IP> 确认密钥登录成功后：
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/; s/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl restart ssh
```

> ⚠️ 执行前先开一个新终端验证 deploy 用户密钥登录可用，否则会把自己锁在门外。

## 3. 拉代码与配置

```bash
su - deploy
git clone https://github.com/gy288666/RAG3.git
cd RAG3/project/deploy
cp .env.production.example .env.production
```

生成并填写密钥：

```bash
openssl rand -hex 32   # 跑两次：分别填入 SECRET_KEY 与 MYSQL_*
openssl rand -hex 16   # CONFIG_ENCRYPTION_KEY 亦可用 32 位 hex
vim .env.production
```

必须修改的项（搜索 `change-me`）：

| 变量 | 要求 |
|---|---|
| `MYSQL_ROOT_PASSWORD` / `MYSQL_PASSWORD` | 强密码；设定后数据库卷初始化即固定，改密码需重建卷 |
| `SECRET_KEY` | JWT 签名密钥，**泄露 = 所有登录态可被伪造** |
| `CONFIG_ENCRYPTION_KEY` | 模型 API Key 的 AES-256 加密密钥，**一经设定不可更改**（否则已保存的 Key 无法解密） |
| `INIT_ADMIN_EMAIL` / `INIT_ADMIN_PASSWORD` | 首次启动自动创建的管理员，上线后立即改密 |

## 4. 启动与验证

### 4.1 构建并启动（首次约 3–5 分钟，含前端 npm 构建）

```bash
docker compose up -d --build
docker compose ps
# 预期: mysql (healthy)、backend (running)、nginx (running)
```

### 4.2 逐项验证

```bash
# ① 健康检查
curl -s http://127.0.0.1/api/health
# 预期: {"code":200,"message":"服务运行正常","data":{"status":"ok",...,"mock_ai":false}}

# ② 前端页面
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1/
# 预期: 200

# ③ 后端日志无异常
docker compose logs backend | tail -5
# 预期: 「RAG 学术知识引擎 v1.1.0 启动完成」「Application startup complete」
```

浏览器打开 `http://<服务器IP>`，用 `INIT_ADMIN_EMAIL/PASSWORD` 登录，**立即在个人设置里修改密码**，然后：

1. 知识库页上传一份 PDF/DOCX/TXT/MD → 状态应从"解析中"变为"已就绪"；
2. 智能问答页提问 → 回答应逐字流式出现，并带可点击的 [n] 引用角标（验证 SSE 无缓冲生效）；
3. 运行监控页 → 应看到刚才问答产生的调用量数据。

三项都通过，服务器端就绪。

## 5. 配置模型服务

登录 → 系统配置：

1. **大模型**：Base URL `https://api.siliconflow.cn/v1`，模型名与 API Key 按需填写（Key 经 AES-256 加密入库，界面只回显掩码）；
2. **Embedding / Rerank**：同样填入模型名与 Key；
3. 保存后发起一次问答，「运行监控」页确认 LLM/向量检索/Rerank 调用次数都在增长。

> 没有外部 Key 时可临时用离线模式联调：`docker compose exec backend sh -c 'DEV_MOCK_AI=true uvicorn app.main:app --port 8001'`——仅限排障，正式服务必须关闭。

## 6. 域名与 HTTPS

前提：域名 A 记录已指向服务器 IP（`ping 你的域名` 返回服务器 IP 再继续）。

```bash
# ① nginx 配置里的 server_name 改成你的域名
sed -i 's/server_name _;/server_name rag.example.com;/' nginx.conf
docker compose up -d --force-recreate nginx

# ② 签发证书（HTTP-01 验证走 nginx 的 80 端口）
docker compose run --rm certbot certonly --webroot -w /var/www/certbot \
    -d rag.example.com --email you@example.com --agree-tos
# 预期: Successfully received certificate

# ③ 让 nginx 加载 443 配置：按 nginx.conf 底部注释的 HTTPS 模板取消注释、
#    替换域名与证书路径，然后 reload
vim nginx.conf && docker compose exec nginx nginx -s reload

# ④ 验证
curl -sI https://rag.example.com | head -1    # 预期: HTTP/2 200
```

**自动续期**（证书 90 天有效）——`crontab -e` 加入：

```cron
0 3 * * 1 cd /home/deploy/RAG3/project/deploy && docker compose run --rm certbot renew >> /home/deploy/backup/certbot.log 2>&1 && docker compose exec -T nginx nginx -s reload
```

## 7. 备份与恢复

### 7.1 备份（crontab 每日 4:00）

```cron
0 4 * * * cd /home/deploy/RAG3/project/deploy && docker compose exec -T mysql sh -c 'mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" rag_high | gzip' > /home/deploy/backup/rag_$(date +\%F).sql.gz && tar czf /home/deploy/backup/data_$(date +\%F).tgz -C /var/lib/docker/volumes/rag3_backend-data/_data . && find /home/deploy/backup -mtime +14 -delete
```

保留 14 天。**重要**：MySQL 与 `backend-data`（chroma + uploads）必须成对备份、成对恢复——向量库存的是文档切片的向量，数据库存的是文档元数据，单边恢复会导致检索与引用对不上。

### 7.2 恢复演练（建议每季度做一次）

```bash
cd /home/deploy/RAG3/project/deploy
docker compose down
tar xzf /home/deploy/backup/data_2026-09-01.tgz -C /var/lib/docker/volumes/rag3_backend-data/_data
docker compose up -d
gunzip < /home/deploy/backup/rag_2026-09-01.sql.gz | docker compose exec -T mysql sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" rag_high'
curl -s http://127.0.0.1/api/health   # 复验
```

## 8. 版本更新与回滚

```bash
# 更新（上游有新版本时）
cd /home/deploy/RAG3 && git pull
cd project/deploy && docker compose up -d --build

# 回滚到上一个版本
git log --oneline -5                 # 找到上一个正常版本的 commit hash
git checkout <hash>
docker compose up -d --build
git checkout main                    # 排障完成后回到主分支
```

数据卷在重建镜像时不受影响；只有 `docker compose down -v` 才会删除卷（**等于删库**，除非有意重置，永远不要加 `-v`）。

## 9. 安全加固清单

- [ ] `.env.production` 中 4 个 `change-me` 已全部替换，该文件未提交 git（已由 .gitignore 拦截）
- [ ] 管理员初始密码已修改
- [ ] HTTPS 生效，浏览器地址栏无"不安全"提示
- [ ] SSH 已改密钥登录、禁 root（第 2.3 节）
- [ ] 安全组仅开放 22（限源 IP）/ 80 / 443
- [ ] 开放注册已评估：当前任何人可用主流邮箱注册；正式对外建议改为邀请制（管理员在用户管理页生成账号）
- [ ] SiliconFlow 控制台设置了余额/用量告警——公开服务意味着额度会被他人消耗
- [ ] `DEV_MOCK_AI=false`（compose 已强制）
- [ ] `docker compose exec backend env | grep SECRET` 确认无明文泄漏到日志

## 10. 故障排查

| 现象 | 诊断与处理 |
|---|---|
| `docker compose up` 后 backend 不断重启 | `docker compose logs backend`——多数是 `.env.production` 漏改或 MySQL 未 healthy；`docker compose ps` 看状态 |
| 数据库连接失败 | 确认 compose 的 `DATABASE_URL`（主机名是 `mysql` 不是 127.0.0.1）；改过 MYSQL_PASSWORD 后旧卷不认新密码：`docker compose down -v` 重建（删数据） |
| 页面能开但登录无反应 | F12 看 Network：请求打到 `/api/...` 了吗？401 检查密码；CORS 报错说明前端没走同源（检查是否直连 8000 端口） |
| 回答整段出现、不逐字 | SSE 被缓冲：确认 `nginx.conf` 中 `proxy_buffering off`；若前面还有 CDN，同样关闭其缓冲 |
| 上传 50MB 文件报 413 | nginx `client_max_body_size` 已设 60m；若套了 CDN 需在 CDN 侧同步调整 |
| 扫描版 PDF 解析很慢 | 走的是 tesseract OCR 回退，正常；批量扫描件建议错峰上传 |
| 「运行监控」日期对不上 | backend 容器时区（compose 已设 `TZ=Asia/Shanghai`），自行改动 compose 时别丢 |
| 证书续期失败 | `docker compose run --rm certbot renew --dry-run` 演练；常见原因是 DNS 变动或 80 端口被占 |
| 磁盘告警 | `docker system df` 看镜像堆积：`docker system prune -f` 清理悬空镜像（不动数据卷） |

## 11. 监控与用量

- **应用层**：管理后台「运行监控」——LLM/Rerank/Embedding 调用次数、Token 消耗、失败率、每日趋势、OCR 失败队列；
- **系统层**：`docker stats`（内存/CPU）、`df -h`（磁盘）、`docker compose logs -f --tail=100 backend`（实时日志）；
- **费用层**：SiliconFlow 控制台的用量与余额是唯一真实的成本信号，建议开启余额低于阈值的通知。

## 12. 卸载

```bash
cd /home/deploy/RAG3/project/deploy
docker compose down            # 停止并移除容器（保留数据卷）
docker compose down -v         # ⚠️ 连数据卷一起删除 = 彻底清空数据库/向量库/上传文件
```

---

## 附：与开发环境的差异

| 项 | 开发（本机） | 生产（本指南） |
|---|---|---|
| 前端 | Vite 开发服务器 :5173，热更新 | 构建进 nginx 镜像，静态托管 |
| 后端 | `uvicorn --reload` 单进程 | uvicorn 2 workers，无 reload |
| 数据库 | 本机 MySQL :3307 或 SQLite | compose 内 mysql8，仅容器网络可达 |
| CORS | localhost:5173 白名单 | 同源，CORS 关闭 |
| 时区 | 依赖本机 | 显式 `TZ=Asia/Shanghai` |
| 模型 Key | `.env` / 管理后台 | 仅管理后台（AES-256 加密入库） |
