# 用户信息管理平台

> Python Flask 安全登录系统  
> 课程作业 / 安全编程实践项目

---

## 📋 项目简介

简易用户信息管理平台，包含**登录、注册、用户搜索、头像上传、个人中心、充值、信息展示、登出**功能。  
本项目从**存在多个安全漏洞的初始版本**开始，历经 **七个阶段安全加固**，累计修复 **56 项安全隐患**。
覆盖了初期安全配置、SQL注入、文件上传、权限提升与业务逻辑、文件包含、CSRF跨站请求伪造、SSRF服务器端请求伪造等 Web 安全核心领域。

---

## 🚀 快速开始

### 环境要求
- Python 3.8+
- Flask
- Werkzeug

### 安装依赖
```bash
pip install flask werkzeug
```

### 启动服务
```bash
python app.py
```

### 访问地址

| 方式 | 地址 | 说明 |
|------|------|------|
| **HTTP 主站** | `http://127.0.0.1:5000` | Kali 本机访问 |
| 局域网访问 | `http://你的局域网IP:5000` | Windows 同网段访问 |

---

## 🔑 测试账号

| 用户名 | 密码 | 角色 | 余额 |
|--------|------|------|------|
| `admin` | `admin123` | 管理员 | 99999 |
| `alice` | `alice2025` | 普通用户 | 100 |

---

## 📁 项目结构

```
user-management/
├── app.py                      # Flask 主应用（含全部安全修复）
├── templates/
│   ├── base.html               # 基础模板（导航栏 + CSRF登出）
│   ├── index.html              # 首页（用户信息 + 搜索功能）
│   ├── login.html              # 登录页面
│   ├── register.html           # 注册页面（含CSRF保护）
│   ├── profile.html            # 个人中心页面
│   └── upload.html             # 上传页面（含文件预览与删除）
├── static/
│   ├── css/
│   │   └── style.css           # 完整样式文件
│   └── uploads/                # 上传文件存储目录
├── pages/
│   └── help.html               # 帮助中心页面（动态加载）
├── reports/                    # 安全审计报告（共7份）
│   ├── SSRF服务器端请求伪造安全审计报告.docx
│   ├── CSRF跨站请求伪造安全审计报告.docx
│   ├── 文件包含漏洞安全审计报告.docx
│   ├── 权限提升与业务逻辑漏洞审计报告.docx
│   ├── 文件上传漏洞安全审计报告.docx
│   ├── SQL注入安全审计报告.docx
│   └── 代码审计报告.docx
├── README.md                   # 本文件
```

---

## 🛡️ 安全修复清单（七阶段，56项）

### 第一阶段：初期安全加固（18项）

涵盖 Debug 模式关闭、密钥强化、密码哈希、CSRF 保护、审计日志、安全响应头、限流等基础安全配置。

| # | 漏洞类型 | 风险等级 | 修复措施 |
|---|----------|----------|----------|
| 1 | Debug模式远程代码执行 | 🔴 严重 | `debug=False` 关闭 Werkzeug Debugger |
| 2 | Session 密钥硬编码 | 🔴 严重 | `os.urandom(24).hex()` 生成强随机密钥 |
| 3 | 明文存储密码 | 🔴 严重 | `werkzeug.security` 哈希存储 + 哈希比对 |
| 4 | HTML注释泄露账号 | 🟠 高危 | 删除登录页中的调试注释 |
| 5 | 密码显示在页面 | 🟠 高危 | 密码字段不再传递给模板 |
| 6 | 监听所有网卡 | 🟠 高危 | 保留 `0.0.0.0`（支持跨机访问） |
| 7 | Session Cookie 缺安全标志 | 🟠 高危 | 添加 `HttpOnly`、`SameSite`、超时 |
| 8 | 无审计日志 | 🟡 中危 | `logging` 记录所有登录事件 |
| 9 | 无登录频率限制 | 🟡 中危 | 内存限流器：每分钟每 IP 最多 5 次 |
| 10 | 无 CSRF 保护 | 🟡 中危 | `secrets.token_hex(32)` 令牌验证 |
| 11 | 无输入校验 | 🟡 中危 | 正则校验 + 长度限制 |
| 12 | 缺安全响应头 | 🟡 中危 | 添加 CSP、X-Frame-Options 等 5 项 |
| 13 | 服务器版本泄露 | 🟡 中危 | Server 响应头清空 |
| 14 | 用户名枚举（时序） | 🟡 中危 | 统一错误提示 + `time.sleep(0.5)` |
| 15 | CSRF 登出（GET） | 🟡 中危 | `/logout` 改为 POST only |
| 16 | Session 无超时 | 🟡 中危 | `PERMANENT_SESSION_LIFETIME=3600` |
| 17 | 密码自动填充 | 🟡 中危 | `autocomplete="off"` |
| 18 | 无验证码 | 🟡 中危 | 限流器覆盖（5次/分钟） |

### 第二阶段：SQL注入修复（6项）⭐

核心修复：f-string 拼接 → 参数化查询 `?` 占位符

| # | 漏洞类型 | 位置 | 修复措施 |
|---|----------|------|----------|
| **19** | **SQL注入** | `/?keyword=`（首页搜索） | 参数化查询 |
| **20** | **SQL注入** | `/search?keyword=`（搜索路由） | 参数化查询 |
| **21** | **SQL注入** | `/register` POST（注册） | 参数化查询 |
| 22 | CSRF缺失 | `/register` | 添加 CSRF Token 验证 |
| 23 | 信息泄露 | 注册错误消息 | 统一错误提示，不暴露数据库细节 |
| 24 | 用户名枚举 | 注册接口 | 通用错误提示 |

**修复原理：** 参数化查询将SQL语句与用户数据**分离编译**，数据库先编译SQL模板，再将参数作为纯数据传入。即使用户输入 `' OR '1'='1`，数据库也只将其当作**普通搜索文本**，而非SQL代码。

```python
# ❌ 修复前
sql = f"SELECT ... WHERE username LIKE '%{keyword}%'"
c.execute(sql)

# ✅ 修复后
sql = "SELECT ... WHERE username LIKE ?"
c.execute(sql, (f'%{keyword}%',))
```

### 第三阶段：文件上传漏洞修复（9项）⭐

核心修复：路径穿越、XSS下载防护、时间戳防覆盖、鉴权路由

| # | 漏洞类型 | 位置 | 修复措施 |
|---|----------|------|----------|
| **25** | **FU-1 路径穿越** | `/upload` | `os.path.basename()` 剥离路径 |
| **26** | **FU-2 超长文件名DoS** | `/upload` | 文件名限制255字符 |
| **27** | **FU-3 HTML上传XSS** | `/static/uploads/` | `Content-Disposition: attachment` 强制下载 |
| 28 | FU-4 SVG脚本注入 | `/static/uploads/` | 非图片文件强制下载 |
| 29 | FU-5 任意文件类型 | `/upload` | 分发控制 |
| 30 | FU-6 同名文件覆盖 | `/upload` | 纳秒级时间戳前缀 |
| 31 | FU-7 文件名特殊字符 | `/upload` | `re.sub()` 过滤危险字符 |
| 32 | FU-8 文件无访问控制 | `/static/uploads/` | `/file/<name>` 鉴权路由 |
| 33 | FU-9 双扩展名绕过 | `/upload` | 时间戳+下载策略覆盖 |

### 第四阶段：权限提升与业务逻辑修复（8项）⭐

核心修复：IDOR越权、未授权操作、CSRF充值、负值扣款、频率限制

| # | 漏洞类型 | 位置 | 修复措施 |
|---|----------|------|----------|
| **34** | **IDOR 越权查看** | `/profile` | 从 session 取 user_id，不接受 URL 参数 |
| **35** | **IDOR 越权充值** | `/recharge` | 从 session 取 user_id，拒绝外部传入 |
| **36** | **未授权操作** | `/profile` `/recharge` | 添加 session 登录校验 |
| **37** | **负值扣款（业务逻辑）** | `/recharge` | `amount <= 0` 拒绝 |
| **38** | **API 滥用** | `/recharge` | 每分钟每 IP 最多 3 次 |
| **39** | **CSRF 缺失** | `/recharge` | 添加 csrf_token 校验 |
| **40** | **金额无上限** | `/recharge` | 单次最多 100 万 |
| **41** | **用户 ID 枚举** | `/profile` | 移除 URL 参数入口 |

### 第五阶段：文件包含漏洞修复（4项）⭐

核心修复：路径穿越 LFI、模板内容注入、链式攻击防护

| # | 漏洞类型 | 位置 | 修复措施 |
|---|----------|------|----------|
| **42** | **FI-1 LFI 路径穿越** | `/page` | `os.path.abspath()` 规范化 + 目录前缀校验 |
| **43** | **FI-2 模板内容注入 XSS** | `index.html` | 移除 `&#124; safe` 过滤器，启用默认转义 |
| **44** | **FI-3 上传+LFI链式攻击** | `/upload` + `/page` | 目录锁定阻断链式攻击 |
| **45** | **FI-4 数据库文件泄露** | `/page` + `data/users.db` | LFI目录锁定阻止读取数据库 |

### 第六阶段：CSRF跨站请求伪造修复（3项）⭐

核心修复：上传CSRF、修改密码CSRF、越权修改密码

| # | 漏洞类型 | 位置 | 修复措施 |
|---|----------|------|----------|
| **46** | **CSRF-1 上传接口CSRF** | `/upload` | 后端添加 csrf_token 校验 + 前端添加隐藏字段 |
| **47** | **CSRF-2 修改密码CSRF** | `/change-password` | 后端添加 csrf_token 校验 + 前端添加隐藏字段 |
| **48** | **CSRF-3 越权修改密码** | `/change-password` | username 从 session 获取 + 增加原密码验证 |

**修复原理：** CSRF Token 校验 + session 隔离 + 原密码验证，三层防护杜绝跨站请求伪造。

```python
# ❌ 修复前：无CSRF、可指定任意username
csrf_token = request.form.get("csrf_token")  # 不存在
username = request.form.get("username", "")  # 可越权

# ✅ 修复后：CSRF校验 + session隔离
if csrf_token != session.get("_csrf_token"):
    abort(403)
username = session.get("username", "")       # 从session获取
old_password = request.form.get("old_password")
```

### 第七阶段：SSRF服务器端请求伪造修复（4项）⭐

核心修复：协议限制、内网地址拦截、错误信息脱敏、CSRF保护

| # | 漏洞类型 | 位置 | 修复措施 |
|---|----------|------|----------|
| **49** | **SSRF-1 file://协议读取文件** | `/fetch-url` | 协议白名单，仅允许 http/https |
| **50** | **SSRF-2 内网地址访问** | `/fetch-url` | IPv4全段+IPv6回环+云元数据拦截 |
| **51** | **SSRF-3 服务指纹泄露** | `/fetch-url` | 错误信息统一脱敏 |
| **52** | **SSRF-4 URL抓取CSRF缺失** | `/fetch-url` | 添加 csrf_token 校验 |

**修复原理：** 五层防护策略——协议白名单、内网IP全量拦截、错误信息脱敏、响应长度控制、CSRF Token校验。

```python
# ❌ 修复前：无任何限制
url = request.form.get("url", "")
req = urllib.request.Request(url)
with urllib.request.urlopen(req) as response:
    raw = response.read()

# ✅ 修复后：多层防护
if not url.lower().startswith(("http://", "https://")):
    return "不支持的协议类型", 400
if _is_internal_ip(hostname):
    return "不允许访问内网地址", 400
# 错误信息脱敏 + CSRF校验

---

## 🔍 最终安全扫描结果

```
文件包含漏洞                         结果
─────────────────────────────────────────────
1.  FI-1 LFI 路径穿越                ✅ os.path.abspath() + 目录校验
2.  FI-2 | safe 内容注入             ✅ 移除 safe 过滤器
3.  FI-3 上传+LFI链式攻击            ✅ 目录锁定阻断
4.  FI-4 数据库文件泄露               ✅ 目录锁定阻止
【权限提升与业务逻辑】
5.  IDOR 越权查看                    ✅ session隔离
6.  越权充值                          ✅ 仅限本人
7.  负值扣款                          ✅ 金额>0校验
8.  批量API攻击                       ✅ 每IP每分钟3次
9.  CSRF充值                          ✅ Token校验
10. 未授权访问                        ✅ 登录拦截
【文件上传】
11. FU-1 路径穿越                    ✅ basename防护
12. FU-2~9 各类上传漏洞              ✅ 全部修复
【SQL注入】
13. UNION SELECT                     ❌ 参数化查询阻止
14. OR '1'='1                        ❌ 参数化查询阻止
15. INSERT注入                       ❌ 参数化查询阻止
【其他安全】
16. 安全响应头 (5项)                 ✅ 全部正确
17. CSRF Token验证                   ✅ 全覆盖
18. 频率限制                         ✅ 5次/分钟
【CSRF跨站请求伪造】
19. 上传接口CSRF                     ✅ Token校验
20. 修改密码CSRF                     ✅ Token校验
21. 越权修改密码                      ✅ session隔离+原密码验证
【SSRF服务器端请求伪造】
22. file:// 协议读取文件                ✅ 协议白名单
23. 内网地址访问                        ✅ IP全量拦截
24. 服务指纹泄露                        ✅ 错误脱敏
25. URL抓取CSRF                        ✅ Token校验
─────────────────────────────────────────────
状态: ✅ 全部56项安全措施已就位
```

---

## ⚙️ 技术栈

- **后端**: Python Flask
- **数据库**: SQLite 3.46.1
- **数据库交互**: sqlite3（全面使用参数化查询）
- **密码存储**: Werkzeug `generate_password_hash` (PBKDF2-SHA256)
- **日志**: Python `logging` 模块
- **前端**: Jinja2 模板 + 原生 CSS

---

## 📝 课程作业说明

本项目的初始版本刻意保留常见安全漏洞，用于教学演示。  
经过 **七个阶段** 安全加固，展示了从基础配置到高级漏洞的完整修复路径。

### 安全修复涉及的知识点

| 知识点 | 对应阶段 |
|--------|----------|
| 安全配置加固（Debug/密钥/密码/响应头等） | 第一阶段 |
| SQL注入与参数化查询 | 第二阶段 |
| 文件上传漏洞（路径穿越/XSS/CSRF等） | 第三阶段 |
| 权限提升与业务逻辑（IDOR/越权/CSRF/限流） | 第四阶段 |
| 文件包含漏洞（LFI/模板注入/链式攻击） | 第五阶段 |
| CSRF跨站请求伪造（Token校验/原密码验证） | 第六阶段 |
| SSRF服务器端请求伪造（协议限制/IP拦截/脱敏） | 第七阶段 |
| 信息泄露防护、认证安全、会话保护 | 全阶段 |
| 暴力破解防护、日志审计 | 全阶段 |

---

## 📋 审计报告

所有审计报告位于 `reports/` 目录下：

- **`SSRF服务器端请求伪造安全审计报告.docx`** — SSRF专题（第七阶段核心）
- **`CSRF跨站请求伪造安全审计报告.docx`** — CSRF专题（第六阶段核心）
- **`文件包含漏洞安全审计报告.docx`** — 文件包含专题（第五阶段核心）
- **`权限提升与业务逻辑漏洞审计报告.docx`** — 权限提升专题（第四阶段核心）
- **`文件上传漏洞安全审计报告.docx`** — 文件上传专题（第三阶段核心）
- **`SQL注入安全审计报告.docx`** — SQL注入专题（第二阶段核心）
- **`代码审计报告.docx`** — 完整安全审计报告

---

## 📄 许可证

MIT License
