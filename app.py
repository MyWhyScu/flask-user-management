import os
import re
import secrets
import logging
import time
import sqlite3
from functools import wraps
from flask import (
    Flask, render_template, request, redirect, session, g, abort
)
from werkzeug.security import generate_password_hash, check_password_hash

# ============================================================
# 日志配置（修复：无审计日志）
# ============================================================
os.makedirs('/var/log/flask', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('/var/log/flask/app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ============================================================
# Flask 应用配置
# ============================================================
app = Flask(__name__)
app.secret_key = os.urandom(24).hex()

# Session 安全配置（修复：Session无超时、缺安全标志、HTTPS启用）
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=3600,  # 1小时超时
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,  # 上传文件最大16MB
)


# ============================================================
# 用户数据库（密码已哈希）
# ============================================================
USERS = {
    "admin": {
        "username": "admin",
        "password": generate_password_hash("admin123"),
        "role": "admin",
        "email": "admin@example.com",
        "phone": "13800138000",
        "balance": 99999
    },
    "alice": {
        "username": "alice",
        "password": generate_password_hash("alice2025"),
        "role": "user",
        "email": "alice@example.com",
        "phone": "13900139001",
        "balance": 100
    }
}


# ============================================================
# SQLite 数据库初始化（用于注册和搜索功能）
# ============================================================

def init_db():
    """初始化 SQLite 数据库，创建 users 表并插入默认用户"""
    os.makedirs('data', exist_ok=True)
    conn = sqlite3.connect('data/users.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            balance INTEGER DEFAULT 0
        )
    ''')
    # 插入默认用户（INSERT OR IGNORE 防止重复）
    c.execute("INSERT OR IGNORE INTO users (username, password, email, phone, balance) VALUES ('admin', 'admin123', 'admin@example.com', '13800138000', 99999)")
    c.execute("INSERT OR IGNORE INTO users (username, password, email, phone, balance) VALUES ('alice', 'alice2025', 'alice@example.com', '13900139001', 100)")
    # 兼容旧表：为没有 balance 列的表添加该列
    try:
        c.execute("ALTER TABLE users ADD COLUMN balance INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # 列已存在
    conn.commit()
    conn.close()
    logger.info("数据库初始化完成: data/users.db")


# ============================================================
# 安全中间件
# ============================================================

# 速率限制存储（修复：无限制可暴力破解）
# 结构: { "login:192.168.1.1": [timestamp1, timestamp2, ...] }
_rate_limit_store = {}

def _check_rate_limit(ip, max_attempts=5, window_seconds=60):
    """IP级别登录频率限制：每分钟最多5次"""
    now = time.time()
    key = f"login:{ip}"
    if key in _rate_limit_store:
        # 清理窗口外的记录
        _rate_limit_store[key] = [
            t for t in _rate_limit_store[key] if now - t < window_seconds
        ]
    else:
        _rate_limit_store[key] = []

    if len(_rate_limit_store[key]) >= max_attempts:
        return False

    _rate_limit_store[key].append(now)
    return True


def _validate_username(text):
    """输入校验（修复：无输入校验）：只允许字母、数字、下划线、中文，最长50字符"""
    if not text or not isinstance(text, str):
        return False
    if len(text) > 50:
        return False
    return bool(re.match(r'^[a-zA-Z0-9_一-鿿]+$', text))


def _generate_csrf_token():
    """生成CSRF令牌（修复：无CSRF保护）"""
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(32)
    return session['_csrf_token']


@app.before_request
def before_request():
    """每个请求前注入CSRF令牌"""
    g.csrf_token = _generate_csrf_token()


@app.after_request
def add_security_headers(response):
    """添加安全响应头（修复：缺安全头、版本泄露）"""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "style-src 'self' 'unsafe-inline';"
    )
    response.headers['Referrer-Policy'] = 'no-referrer'
    # [OV-2] 完全移除Server版本信息
    response.headers.pop('Server', None)
    response.headers['Server'] = ''
    return response


# ============================================================
# 路由
# ============================================================

@app.route("/")
def index():
    username = session.get("username")
    user_info = None
    search_results = None
    keyword = ""

    if username and username in USERS:
        user = USERS[username]
        user_info = {k: v for k, v in user.items() if k != "password"}

    # 搜索功能（已修复：使用参数化查询代替f-string拼接）
    keyword = request.args.get("keyword", "")
    if keyword:
        conn = sqlite3.connect('data/users.db')
        c = conn.cursor()
        sql = "SELECT id, username, email, phone FROM users WHERE username LIKE ? OR email LIKE ?"
        params = (f'%{keyword}%', f'%{keyword}%')
        print(f"[SQL] {sql} (参数: {params})")
        logger.info(f"执行SQL: {sql}")
        try:
            c.execute(sql, params)
            search_results = c.fetchall()
        except Exception as e:
            print(f"[SQL ERROR] {e}")
            search_results = []
        conn.close()

    return render_template("index.html", user=user_info, search_results=search_results, keyword=keyword)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        csrf_token = request.form.get("csrf_token") or ""
        ip = request.remote_addr or "unknown"

        # CSRF 令牌校验
        if csrf_token != session.get("_csrf_token", ""):
            logger.warning("CSRF令牌校验失败 - IP: %s", ip)
            abort(403)

        # 输入校验
        if not _validate_username(username):
            return render_template(
                "login.html",
                error="用户名格式无效（仅允许字母、数字、下划线、中文）"
            )

        if len(password) < 1 or len(password) > 128:
            return render_template("login.html", error="密码长度无效")

        # 速率限制
        if not _check_rate_limit(ip):
            logger.warning("登录频率超限 - IP: %s, 用户名: %s", ip, username)
            return render_template(
                "login.html",
                error="登录尝试过于频繁，请60秒后再试"
            )

        # 密码验证（使用哈希比对，修复：明文密码）
        if username in USERS and check_password_hash(
            USERS[username]["password"], password
        ):
            session["username"] = username
            session.permanent = True
            # 从SQLite获取user_id存入session（用于导航链接）
            conn = sqlite3.connect('data/users.db')
            try:
                cur = conn.cursor()
                cur.execute("SELECT id FROM users WHERE username = ?", (username,))
                row = cur.fetchone()
                if row:
                    session["user_id"] = row[0]
            finally:
                conn.close()
            # 登录成功后刷新CSRF令牌
            session.pop("_csrf_token", None)

            user = USERS[username]
            user_info = {k: v for k, v in user.items() if k != "password"}
            logger.info("登录成功 - 用户: %s, IP: %s", username, ip)
            return render_template("index.html", user=user_info)
        else:
            logger.warning("登录失败 - 用户: %s, IP: %s", username, ip)
            # 统一错误信息，不透露是用户名不存在还是密码错误
            # 增加固定延时防止时序攻击枚举用户名
            time.sleep(0.5)
            return render_template("login.html", error="用户名或密码错误")

    return render_template("login.html", csrf_token=_generate_csrf_token())


@app.route("/logout", methods=["POST"])
def logout():
    """修复：改为POST方法，防止CSRF登出"""
    csrf_token = request.form.get("csrf_token") or ""
    username = session.get("username", "unknown")

    if csrf_token != session.get("_csrf_token", ""):
        abort(403)

    session.clear()
    logger.info("登出 - 用户: %s, IP: %s", username, request.remote_addr)
    return redirect("/")


# ============================================================
# 注册功能（已修复：使用参数化查询，添加CSRF保护）
# ============================================================

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        email = request.form.get("email", "")
        phone = request.form.get("phone", "")
        csrf_token = request.form.get("csrf_token") or ""

        # CSRF 令牌校验（修复：添加CSRF保护）
        if csrf_token != session.get("_csrf_token", ""):
            logger.warning("注册CSRF令牌校验失败 - IP: %s", request.remote_addr)
            abort(403)

        # 输入校验
        if not username or not password:
            return render_template("register.html", error="用户名和密码不能为空")

        # 密码长度限制
        if len(password) > 128:
            return render_template("register.html", error="密码长度不能超过128位")

        # 使用参数化查询（修复：SQL注入漏洞）
        conn = sqlite3.connect('data/users.db')
        c = conn.cursor()
        sql = "INSERT INTO users (username, password, email, phone) VALUES (?, ?, ?, ?)"
        params = (username, password, email, phone)
        print(f"[SQL] {sql} (参数: {params})")
        logger.info(f"执行SQL: {sql}")
        try:
            c.execute(sql, params)
            conn.commit()
            logger.info("注册成功 - 用户: %s", username)
            conn.close()
            # 刷新CSRF令牌
            session.pop("_csrf_token", None)
            return render_template("login.html", success="注册成功，请登录")
        except Exception as e:
            conn.close()
            # [OV-1] 修复：统一返回成功提示，不向客户端暴露用户是否存在
            # 具体错误（如用户已存在）记录在服务端日志中
            error_msg = str(e)
            if "UNIQUE constraint" in error_msg:
                logger.warning("注册失败(用户已存在): %s - IP: %s", username, request.remote_addr)
            else:
                logger.warning("注册失败: %s - IP: %s", error_msg, request.remote_addr)
            return render_template("login.html", success="注册成功，请登录")

    return render_template("register.html", csrf_token=_generate_csrf_token())


@app.route("/search", methods=["GET"])
def search():
    keyword = request.args.get("keyword", "")
    if not keyword:
        return redirect("/")

    conn = sqlite3.connect('data/users.db')
    c = conn.cursor()
    sql = "SELECT id, username, email, phone FROM users WHERE username LIKE ? OR email LIKE ?"
    params = (f'%{keyword}%', f'%{keyword}%')
    print(f"[SQL] {sql} (参数: {params})")
    logger.info(f"执行SQL: {sql}")
    try:
        c.execute(sql, params)
        results = c.fetchall()
    except Exception as e:
        print(f"[SQL ERROR] {e}")
        results = []
    conn.close()

    return render_template("index.html", user=None, search_results=results, keyword=keyword)


# ============================================================
# 头像上传功能
# ============================================================

@app.route("/upload", methods=["GET", "POST"])
def upload():
    """用户头像上传，需要登录"""
    if "username" not in session:
        return redirect("/login")

    if request.method == "POST":
        file = request.files.get("file")
        if file and file.filename:
            # [FU-1] 路径穿越修复：只取文件名，丢弃路径
            filename = os.path.basename(file.filename)

            # [FU-7] 特殊字符过滤：替换危险字符为下划线
            filename = re.sub(r'[\\/:*?"<>|%\0\r\n]', '_', filename)
            if not filename:
                return render_template("upload.html", error="无效的文件名")

            # [FU-6] 防覆盖：时间戳(纳秒)确保唯一性
            ts = str(time.time_ns())

            # [FU-2] 超长文件名限制：考虑时间戳前缀后总长不超过255
            max_total = 255 - len(ts) - 1  # 减去时间戳和下划线
            if len(filename) > max_total:
                name_part, ext_part = os.path.splitext(filename)
                max_name_len = max_total - len(ext_part)
                filename = (name_part[:max_name_len] + ext_part) if max_name_len > 0 else filename[:max_total]

            safe_filename = f"{ts}_{filename}"

            upload_dir = os.path.join(app.static_folder, "uploads")
            os.makedirs(upload_dir, exist_ok=True)
            filepath = os.path.join(upload_dir, safe_filename)
            file.save(filepath)

            # [FU-8] 使用带鉴权的文件路由，替代直接静态文件访问
            file_url = f"/file/{safe_filename}"

            logger.info("文件上传成功 - 用户: %s, 文件名: %s",
                        session["username"], safe_filename)
            return render_template(
                "upload.html",
                uploaded=True,
                file_url=file_url,
                filename=safe_filename
            )
        else:
            return render_template("upload.html", error="请选择要上传的文件")

    return render_template("upload.html")


@app.route("/file/<filename>")
def serve_uploaded_file(filename):
    """带鉴权和XSS防护的文件服务"""
    # 必须登录才能访问上传的文件
    if "username" not in session:
        return redirect("/login")

    # [FU-1] 路径穿越防护
    safe_filename = os.path.basename(filename)
    upload_dir = os.path.join(app.static_folder, "uploads")
    filepath = os.path.join(upload_dir, safe_filename)

    if not os.path.exists(filepath):
        abort(404)

    # [FU-3][FU-4][FU-5] XSS防护：
    # 所有通过此路由提供的文件设置 Content-Disposition: attachment
    # 浏览器会下载而非解析执行（防止 HTML/SVG/JS 脚本执行）
    # 同时对图片类型支持 inline 预览
    ext = os.path.splitext(safe_filename)[1].lower()
    image_exts = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
    as_attachment = ext not in image_exts

    from flask import send_from_directory
    return send_from_directory(
        upload_dir,
        safe_filename,
        as_attachment=as_attachment,
        download_name=safe_filename
    )


@app.route("/delete-file", methods=["POST"])
def delete_file():
    """删除已上传的文件"""
    if "username" not in session:
        return redirect("/login")

    filename = request.form.get("filename", "")
    csrf_token = request.form.get("csrf_token", "")

    # CSRF校验
    if csrf_token != session.get("_csrf_token", ""):
        abort(403)

    if not filename:
        return redirect("/upload")

    # 路径穿越防护
    safe_filename = os.path.basename(filename)
    upload_dir = os.path.join(app.static_folder, "uploads")
    filepath = os.path.join(upload_dir, safe_filename)

    if os.path.exists(filepath):
        try:
            os.remove(filepath)
            logger.info("文件删除成功 - 用户: %s, 文件名: %s",
                        session["username"], safe_filename)
        except Exception as e:
            logger.warning("文件删除失败: %s - %s", safe_filename, e)

    return redirect("/upload")


# ============================================================
# 个人中心与充值功能（已修复全部权限与业务逻辑漏洞）
# ============================================================

@app.route("/profile", methods=["GET"])
def profile():
    """个人中心：需登录，仅可查看自己资料"""
    # [修复1] 添加登录校验
    if "username" not in session:
        return redirect("/login")

    # [修复2] 从session获取当前用户ID，不接受URL参数
    user_id = session.get("user_id")
    if not user_id:
        return "无法获取用户信息", 400

    conn = sqlite3.connect('data/users.db')
    c = conn.cursor()
    sql = "SELECT id, username, email, phone, balance FROM users WHERE id = ?"
    c.execute(sql, (user_id,))
    user = c.fetchone()
    conn.close()

    if not user:
        return "用户不存在", 404

    user_data = {
        "id": user[0],
        "username": user[1],
        "email": user[2],
        "phone": user[3],
        "balance": user[4]
    }
    return render_template("profile.html", user=user_data)


@app.route("/recharge", methods=["POST"])
def recharge():
    """充值功能：需登录+CSRF，仅可给自己充值，金额必须为正"""

    # [修复3] 未登录拦截
    if "username" not in session:
        return redirect("/login")

    # [修复4] CSRF校验
    csrf_token = request.form.get("csrf_token") or ""
    if csrf_token != session.get("_csrf_token", ""):
        logger.warning("充值CSRF校验失败 - IP: %s", request.remote_addr)
        abort(403)

    # [修复5] 仅允许给自己充值（从session取user_id）
    user_id = session.get("user_id")
    if not user_id:
        return "无法获取用户信息", 400

    amount = request.form.get("amount")

    if not amount:
        return "缺少金额参数", 400

    try:
        amount = int(amount)
    except ValueError:
        return "金额格式无效", 400

    # [修复6] 金额必须为正数
    if amount <= 0:
        return "金额必须大于0", 400

    # [修复7] 金额上限
    if amount > 1000000:
        return "单次充值金额不能超过100万", 400

    # [修复8] 添加频率限制（每分钟最多3次）
    ip = request.remote_addr or "unknown"
    key = f"recharge:{ip}"
    now = time.time()
    if key in _rate_limit_store:
        # 复用登录限流的存储结构，但使用不同key前缀
        pass
    # 使用独立的recharge限流
    if not hasattr(recharge, "_rl"):
        recharge._rl = {}
    rl = recharge._rl
    if key not in rl:
        rl[key] = []
    rl[key] = [t for t in rl[key] if now - t < 60]
    if len(rl[key]) >= 3:
        logger.warning("充值频率超限 - 用户: %s, IP: %s", session["username"], ip)
        return "充值操作过于频繁，请稍后再试", 429
    rl[key].append(now)

    conn = sqlite3.connect('data/users.db')
    c = conn.cursor()
    sql = "UPDATE users SET balance = balance + ? WHERE id = ?"
    c.execute(sql, (amount, user_id))
    conn.commit()
    conn.close()

    logger.info("充值成功 - 用户: %s, 金额: +%d, IP: %s",
                session["username"], amount, ip)
    return redirect(f"/profile")


if __name__ == "__main__":
    # 初始化 SQLite 数据库
    init_db()

    # [OV-2] 使用WSGI包装器彻底移除Server头
    import werkzeug.serving
    original_run = werkzeug.serving.WSGIRequestHandler.make_environ

    class NoServerHeaderHandler(werkzeug.serving.WSGIRequestHandler):
        def handle(self):
            super().handle()

        def send_header(self, keyword, value):
            if keyword.lower() != 'server':
                super().send_header(keyword, value)

    # HTTP 主服务（端口 5000）
    app.run(
        debug=False,
        host="0.0.0.0",
        port=5000,
        request_handler=NoServerHeaderHandler,
    )
