# 登录与外网访问配置

本次只修改代码，没有连接服务器、修改 DNS、开放端口或执行部署。网页登录是**单个个人账号**：登录后访问同一份文献库，不提供注册、多个用户或多人数据隔离。

## 本机设置

在仓库根目录初始化账号，密码在终端交互输入，不写入命令参数或代码：

```sh
./setup-account.sh init --username oursus
./start-web.sh
```

打开 `http://localhost:3017`，会先进入登录页。没有初始化账号时显示设置提示，文献和笔记接口保持关闭。没有默认账号或默认密码。

密码至少 12 个字符。忘记密码时执行：

```sh
./setup-account.sh reset --username oursus
```

账号文件与现有设置同目录，启动器默认 `.web-settings/web-auth.json`，只保存随机盐与 PBKDF2-HMAC-SHA256 哈希（600,000 次），权限为 600；重置账号立即使旧会话在下一次请求时失效。不要把 `.web-settings` 或 `.env` 上传到公共仓库。

## 固定域名配置（留待自行部署）

推荐用 HTTPS 反向代理作为外网入口，Python 服务处于内网。仓库已提供 `Dockerfile`、`compose.yaml`、`.env.example` 和 `deploy/Caddyfile`。这些配置未在本次环境运行 Docker 构建或部署。

未来部署时，在服务器仓库中准备域名配置：

```sh
cp .env.example .env
# 编辑 .env，将 TEXTFOLD_DOMAIN 改为自己的域名，例如 read.your-domain.com
docker compose build
docker compose run --rm textfold python -m textfold account init --username oursus
docker compose up -d
```

域名需要解析到该服务器，80/443 端口需可达。Caddy 自动处理 HTTPS；应用的 3017 端口不映射到公网。文献与账号配置分别保存在 `library`、`settings` 卷中，Caddy 证书也有独立持久化卷。不要删除这些卷作为日常更新操作。

容器中没有你本机的 Codex、Pi 或其登录状态。首次登录后在设置中添加 API 供应商和模型，才能生成折叠层级、翻译或问答；内置示例可直接阅读。配置没有复制本机文献、API Key 或模型凭据。

## 使用已有反向代理

如果服务器已有 Nginx、Caddy 或面板，可复用它，把 HTTPS 域名代理到回环地址 `127.0.0.1:3017`。反向代理需要保留浏览器发送的公开 `Host`，例如 `read.your-domain.com`，而非替换成上游地址。

```sh
TEXTFOLD_PUBLIC_ORIGIN=https://read.your-domain.com ./start-web.sh
```

默认只监听 `127.0.0.1`，适用于同机反向代理。容器网络等需要绑定全部接口时，可设置 `TEXTFOLD_BIND_HOST=0.0.0.0`，但服务会检查网页模式、登录保护和 HTTPS 公开地址是否全部配置。

`TEXTFOLD_PUBLIC_ORIGIN` 必须是单个完整 HTTPS 源，不允许通配符、路径、查询参数或内嵌账号。服务只接受这个公开 Host 与本机 Host；不会根据客户端发送的 `X-Forwarded-Host` 或 `X-Forwarded-Proto` 放宽校验。认证启用后，所有写请求的 `Origin` 必须与对应入口完全一致，包括协议和端口。

也可直接使用 Python 入口（注意账号初始化和启动使用相同的 `TEXTFOLD_HOME`）：

```sh
python -m textfold account init --username oursus
python -m textfold serve --web --auth --public-origin https://read.your-domain.com
```

## 登录行为

- 未登录访问首页或阅读页会跳转登录，成功后回到原页面；只允许站内返回地址。
- 文献、图片、PDF、笔记、导出和模型设置接口都受保护，未登录返回 401。
- HTTPS 入口使用 `Secure`、`HttpOnly`、`SameSite=Lax`、`Path=/` 的 `__Host-` Cookie；令牌不会放进网页存储或返回 JSON。
- 未勾选“保存登录”时使用浏览器会话 Cookie，最长 12 小时、连续 2 小时无请求后失效；重启服务也会使这种临时会话失效。
- 勾选“保存登录”后在当前设备保留 30 天，关闭浏览器或重启服务后仍然有效。服务端只在私有设置目录的 `web-sessions.sqlite3` 保存令牌哈希，不保存密码或原始令牌；退出登录及重置账号会撤销已保存的登录。
- 每个来源 5 分钟最多尝试登录 10 次，另有全局限制和密码验证并发限制。代理后的来源统一按代理地址计数，不信任可伪造的转发 IP。
- 登录页不加载文献库数据；对密码错误和账号不存在使用同一提示。

这仍是个人服务。请不要把个人账号共享给其他人；账号可管理文献和模型设置，模型调用使用服务端配置的额度。多人使用需要另行实现用户和数据隔离。
