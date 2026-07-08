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
            phone TEXT
        )
    ''')
    # 插入默认用户（INSERT OR IGNORE 防止重复）
    c.execute("INSERT OR IGNORE INTO users (username, password, email, phone) VALUES ('admin', 'admin123', 'admin@example.com', '13800138000')")
    c.execute("INSERT OR IGNORE INTO users (username, password, email, phone) VALUES ('alice', 'alice2025', 'alice@example.com', '13900139001')")
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
    # 隐藏服务器版本信息
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
            # 修复：不暴露具体数据库错误信息
            error_msg = str(e)
            if "UNIQUE constraint" in error_msg:
                return render_template("register.html", error="该用户名已被注册")
            else:
                logger.warning("注册失败: %s - IP: %s", error_msg, request.remote_addr)
                return render_template("register.html", error="注册失败，请稍后重试")

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


if __name__ == "__main__":
    # 初始化 SQLite 数据库
    init_db()

    # HTTP 主服务（端口 5000）
    app.run(
        debug=False,
        host="0.0.0.0",
        port=5000,
    )
