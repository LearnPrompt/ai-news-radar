# GitHub Pages 自定义域名 HTTPS 恢复

适用入口：`https://news.learnprompt.pro/`。`learnprompt.pro` 和 `www.learnprompt.pro` 是其他入口，不能用它们的 200 代替新闻子域验收。

## 2026-10-25 故障证据

- 新闻子域返回 Cloudflare HTTP 526。
- GitHub Pages 仍为 `built`，发布源为 `master` 根目录，`cname` 为 `news.learnprompt.pro`。
- Pages API 的 `https_certificate.state` 为 `bad_authz`，`expires_at` 为 `2026-10-12`。
- 以 `news.learnprompt.pro` 为 SNI 直连 GitHub Pages 地址 `185.199.108.153:443`，正常 TLS 校验报证书过期；读取到的证书 SAN 包含 `news.learnprompt.pro`，签发者为 Let's Encrypt YR1，实际到期时间为 **2026-10-12 12:05:21 UTC**。

已确认源站证书过期；续签失败的具体原因尚待 Cloudflare DNS/代理与 GitHub 域名配置核对。公开 DNS 只能看到 Cloudflare 地址，不能据此推断后台 CNAME 的实际目标。

静态页面、采集代码或 `CNAME` 文本变更不能直接给 GitHub Pages 续签证书。合并本分支本身不等于线上修复。数据更新 Actions 成功也不等于站点可访问。

## 本次恢复结果

2026-10-25 已将 `news` 单条 CNAME 改为 DNS only，目标仍为 `learnprompt.github.io`；读取全部 18 条 DNS 记录，确认其余 17 条未变。重新绑定同一 Pages 域名后，证书状态变为 `approved`，直连源站的正常 TLS 校验通过，新证书到期时间为 **2027-01-23 07:13:26 UTC**。首页、robots、sitemap、latest 数据和新鲜 Pages 证书元数据五项检查均通过。

Pages 的 Enforce HTTPS 已保存为启用。保持新闻子域 DNS only，使请求直接由 Pages 的有效证书服务；未修改其他子域和全域 SSL 安全级别。此次线上恢复来自域名与证书配置处理，本分支保留排错与验收工具供后续复用。

## 处理步骤

1. 在有权限的 Cloudflare 账户中确认真实 `learnprompt.pro` zone，读取并备份 **仅 `news.learnprompt.pro`** 的 DNS 类型、目标、TTL、代理状态及相关规则。保留根域、`www`、`v1` 和其他记录。
2. 在仓库 Settings → Pages 确认发布源和域名仍为上述值。新闻子域的预期 DNS 为 `CNAME news → LearnPrompt.github.io`，目标不带 `/ai-news-radar/` 路径。检查冲突的 A/AAAA 记录和实际适用的 CAA 限制；如果存在 CAA，必须允许 `letsencrypt.org`。
3. 如实际记录有误，只修正已确认的新闻子域记录。如代理或规则阻挡域名验证，在记录原值后将 **news 单条** 切为 DNS only，让 Pages 完成验证。证书尚未恢复前，直连可能报证书错误，不能将代理切换当作恢复。
4. 等待 DNS 和 GitHub 的 HTTPS 检查更新。仍处于 `bad_authz` 时，按 GitHub 官方流程移除并重新添加 Pages 的同一自定义域名，以重启证书签发；操作前确认域名所有权和恢复值，尽量缩短移除窗口。此步骤是生产设置变更，可能让 GitHub 在发布分支更新 `CNAME`，应先审阅实际差异，不能用更改本地修复分支代替。
5. 等 `https_certificate.state` 成为 `approved` 且有效期在未来，再启用 Pages 的 Enforce HTTPS。Cloudflare 如保留代理，保持 Full (strict)，并复测公开入口；不以降为 Full/Flexible 或关闭证书校验来消除 526。如保留 DNS only，正常 TLS 验证和同一域名验收仍必须通过。
6. 保存操作前后配置与检查回执。中途受登录、权限或签发延迟阻塞时，保留当前失败状态和精确时间，不标已恢复。

## 恢复验收

在仓库根目录执行（只读；`gh` 使用已配置的认证，不把凭证写进命令）：

```bash
gh api repos/LearnPrompt/ai-news-radar/pages > /tmp/radar-pages.json
python3 scripts/check_pages_health.py --pages-json /tmp/radar-pages.json
```

检查器验证根目录 `CNAME` 对应的 HTTPS 主机：首页、`robots.txt`、`sitemap.xml` 和 `data/latest-24h.json` 必须返回正常内容；跨主机跳转不算同一入口恢复。提供 Pages API 回执时，还会核验域名、证书签发状态和有效期。未提供 `--pages-json` 时只核验公开 HTTP/TLS 请求，不宣称已验 GitHub 源站证书。

`0` 表示所声明范围的检查通过，`1` 表示检查失败，`2` 表示输入无效。以脚本 JSON 输出的范围与缺口为准。不要用 `curl -k`、缓存页面、其他域名 200 或一次成功的数据生成任务代替验收。正常正文读取与证书状态都通过后，才清除该 hostname 的故障；站点访问成功不代表资讯数据足够新，数据时效继续按 `generated_at` 单独核对。

本工具按需运行，未新增定时任务、通知、遥测或自动配置修改。

## 官方参考

- [GitHub：HTTPS 证书签发与重新触发](https://docs.github.com/en/pages/getting-started-with-github-pages/securing-your-github-pages-site-with-https)
- [GitHub：自定义域名、DNS 与 CAA 排错](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/troubleshooting-custom-domains-and-github-pages)
- [Cloudflare：Error 526](https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-5xx-errors/error-526/)
