import os
import re
import secrets
import logging
import time
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
    SESSION_COOKIE_SECURE=True,
    PERMANENT_SESSION_LIFETIME=3600,  # 1小时超时
)

# HTTPS 证书位置: /root/certs/cert.pem
# HTTP 重定向端口: 5080 （自动跳转到 HTTPS 5000）


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
    if username and username in USERS:
        user = USERS[username]
        # 不将密码字段传递给模板
        user_info = {k: v for k, v in user.items() if k != "password"}
    return render_template("index.html", user=user_info)


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


if __name__ == "__main__":
    import threading

    def run_http_redirect():
        """HTTP 重定向服务（端口 5080 → 强制跳转到 HTTPS 5000）"""
        from flask import Flask, redirect, request

        redirect_app = Flask(__name__)

        @redirect_app.route("/")
        @redirect_app.route("/<path:path>")
        def redirect_to_https(path=""):
            host = request.host.split(":")[0]
            return redirect(f"https://{host}:5000/{path}")

        redirect_app.run(debug=False, host="0.0.0.0", port=5080)

    # 启动 HTTP 重定向线程（端口 5080）
    t = threading.Thread(target=run_http_redirect, daemon=True)
    t.start()

    # HTTPS 主服务（端口 5000）
    app.run(
        debug=False,
        host="0.0.0.0",
        port=5000,
        ssl_context=("/root/certs/cert.pem", "/root/certs/key.pem")
    )
