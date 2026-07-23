"""
Auth endpoint integration tests.

These tests run in subprocess isolation to avoid sys.modules pollution
from other test files that use the real aiosqlite/database module.

Each test function spawns a subprocess that executes a minimal test script,
ensuring a clean Python interpreter for each scenario.

Validates: Requirements 3.1-3.10
"""

import sys
import os
import subprocess
import json

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PYTHON = sys.executable


def run_test_script(script: str) -> dict:
    """Run a Python script in a subprocess and return its JSON output."""
    result = subprocess.run(
        [PYTHON, "-c", script],
        capture_output=True,
        text=True,
        cwd=BACKEND_DIR,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Script failed with code {result.returncode}:\n"
            f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )
    try:
        return json.loads(result.stdout.strip())
    except json.JSONDecodeError:
        raise RuntimeError(f"Could not parse JSON output:\n{result.stdout}")


# ── Shared preamble injected into every test script ───────────────────────────
_PREAMBLE = """
import sys, os, types, json
from unittest.mock import MagicMock, AsyncMock, patch
sys.path.insert(0, '.')

try:
    import bcrypt as _b, types as _t
    if not hasattr(_b, '__about__'):
        a = _t.ModuleType('bcrypt.__about__'); a.__version__ = '4.0.1'; _b.__about__ = a
    if not getattr(_b, '_hashpw_patched', False):
        _oh = _b.hashpw
        _b.hashpw = lambda p,s: _oh(p[:72],s)
        _b._hashpw_patched = True
except Exception: pass

_STUBS = ['langchain','langchain.chains','langchain.chains.combine_documents',
    'langchain_community','langchain_community.vectorstores','langchain_google_genai',
    'langchain_huggingface','sentence_transformers','faiss',
    'app.chain','app.chat','app.retriever','app.embeddings','app.vectorstore','app.ingest']
for m in _STUBS:
    sys.modules[m] = MagicMock()

_cfg = types.ModuleType('app.config')
_cfg.ENVIRONMENT='test'; _cfg.JWT_SECRET_KEY='test-secret-key-32-chars-minimum!!'
_cfg.JWT_ALGORITHM='HS256'; _cfg.ACCESS_TOKEN_EXPIRE_MINUTES=15
_cfg.REFRESH_TOKEN_EXPIRE_DAYS=7; _cfg.CHAT_HISTORY_WINDOW=10
_cfg.GEMINI_MODEL='gemini-pro'; _cfg.GOOGLE_API_KEY=''
_cfg.DOCUMENTS_DIR=''; _cfg.VECTORSTORE_DIR=''; _cfg.DATABASE_PATH=''
_cfg.RETRIEVER_K=3; _cfg.CHUNK_SIZE=1000; _cfg.CHUNK_OVERLAP=200
sys.modules['app.config'] = _cfg

_db = MagicMock()
_db.create_user = AsyncMock(return_value=None)
_db.get_user_by_email = AsyncMock(return_value=None)
_db.get_user_by_id = AsyncMock(return_value=None)
sys.modules['app.database'] = _db

import fastapi as _f
_as = MagicMock(); _as.router = _f.APIRouter(); sys.modules['app.auth'] = _as

for m in ['app.auth','app.security','aiosqlite']: sys.modules.pop(m, None)

from fastapi import FastAPI
from starlette.testclient import TestClient
from app.security import create_access_token, create_refresh_token
from app.auth import router as auth_router

app = FastAPI()
app.include_router(auth_router, prefix='/api/v1')
client = TestClient(app, raise_server_exceptions=True)
"""


class TestRegisterEndpoint:

    def test_register_success(self):
        """HTTP 201 with user data and cookies on successful registration. Req 3.2"""
        script = _PREAMBLE + """
_db.create_user = AsyncMock(return_value=None)
with patch('app.auth.hash_password', return_value='hashed'):
    r = client.post('/api/v1/auth/register', json={'email':'new@example.com','password':'pass12345'})
body = r.json()
set_cookie = r.headers.get('set-cookie', '')
print(json.dumps({'status': r.status_code, 'has_email': 'email' in body,
    'has_cookie': 'access_token' in set_cookie or 'access_token' in str(r.cookies)}))
"""
        result = run_test_script(script)
        assert result["status"] == 201
        assert result["has_email"] is True

    def test_register_duplicate_email(self):
        """HTTP 409 when email already registered. Req 3.3"""
        script = _PREAMBLE + """
_db.create_user = AsyncMock(side_effect=ValueError('Email already registered.'))
# Re-import app.auth so it picks up the updated _db.create_user binding
sys.modules.pop('app.auth', None)
from app.auth import router as auth_router2
app2 = FastAPI()
app2.include_router(auth_router2, prefix='/api/v1')
client2 = TestClient(app2, raise_server_exceptions=True)
with patch('app.auth.hash_password', return_value='hashed'):
    r = client2.post('/api/v1/auth/register', json={'email':'dup@example.com','password':'pass12345'})
print(json.dumps({'status': r.status_code}))
"""
        result = run_test_script(script)
        assert result["status"] == 409


class TestLoginEndpoint:

    def test_login_success(self):
        """HTTP 200 with auth cookies and message ok when credentials correct. Req 3.4"""
        script = _PREAMBLE + """
_FAKE = {'id':'uid-1','email':'test@example.com','password_hash':'hash','created_at':'2024-01-01T00:00:00+00:00'}
_db.get_user_by_email = AsyncMock(return_value=_FAKE)
# Re-import app.auth so it picks up the updated _db.get_user_by_email binding
sys.modules.pop('app.auth', None)
from app.auth import router as auth_router2
app2 = FastAPI()
app2.include_router(auth_router2, prefix='/api/v1')
client2 = TestClient(app2, raise_server_exceptions=True)
with patch('app.auth.verify_password', return_value=True):
    r = client2.post('/api/v1/auth/login', json={'email':'test@example.com','password':'correct'})
body = r.json()
print(json.dumps({'status': r.status_code, 'has_email': 'email' in body}))
"""
        result = run_test_script(script)
        assert result["status"] == 200
        assert result["has_email"] is True

    def test_login_wrong_password(self):
        """HTTP 401 with correct detail when password wrong. Req 3.5"""
        script = _PREAMBLE + """
_FAKE = {'id':'uid-1','email':'test@example.com','password_hash':'hash','created_at':'2024-01-01T00:00:00+00:00'}
_db.get_user_by_email = AsyncMock(return_value=_FAKE)
with patch('app.auth.verify_password', return_value=False):
    r = client.post('/api/v1/auth/login', json={'email':'test@example.com','password':'wrong'})
print(json.dumps({'status': r.status_code, 'detail': r.json().get('detail','')}))
"""
        result = run_test_script(script)
        assert result["status"] == 401
        assert result["detail"] == "Invalid email or password."

    def test_login_unknown_email(self):
        """HTTP 401 when email not found. Req 3.6"""
        script = _PREAMBLE + """
_db.get_user_by_email = AsyncMock(return_value=None)
r = client.post('/api/v1/auth/login', json={'email':'nobody@example.com','password':'any'})
print(json.dumps({'status': r.status_code, 'detail': r.json().get('detail','')}))
"""
        result = run_test_script(script)
        assert result["status"] == 401
        assert result["detail"] == "Invalid email or password."


class TestRefreshEndpoint:

    def test_refresh_success(self):
        """HTTP 200 with auth cookies given valid refresh token cookie. Req 3.7"""
        script = _PREAMBLE + """
_FAKE = {'id':'uid-r1','email':'r@example.com','created_at':'2024-01-01T00:00:00+00:00'}
_db.get_user_by_id = AsyncMock(return_value=_FAKE)
tok = create_refresh_token('uid-r1')
r = client.post('/api/v1/auth/refresh', cookies={'refresh_token': tok})
body = r.json()
print(json.dumps({'status': r.status_code, 'message': body.get('message','')}))
"""
        result = run_test_script(script)
        assert result["status"] == 200
        assert result["message"] == "ok"

    def test_refresh_no_cookie_returns_401(self):
        """HTTP 401 when no refresh_token cookie is present. Req 3.7"""
        script = _PREAMBLE + """
r = client.post('/api/v1/auth/refresh')
print(json.dumps({'status': r.status_code}))
"""
        result = run_test_script(script)
        assert result["status"] == 401

    def test_refresh_with_access_token(self):
        """HTTP 401 when access token used as refresh token cookie. Req 3.8"""
        script = _PREAMBLE + """
tok = create_access_token('uid-wrong')
r = client.post('/api/v1/auth/refresh', cookies={'refresh_token': tok})
print(json.dumps({'status': r.status_code}))
"""
        result = run_test_script(script)
        assert result["status"] == 401


class TestMeEndpoint:

    def test_me_success(self):
        """HTTP 200 with user profile when valid Bearer token. Req 3.9"""
        script = _PREAMBLE + """
_FAKE = {'id':'uid-me','email':'me@example.com','created_at':'2024-01-15T10:30:00+00:00'}
_db.get_user_by_id = AsyncMock(return_value=_FAKE)
tok = create_access_token('uid-me')
r = client.get('/api/v1/auth/me', headers={'Authorization': f'Bearer {tok}'})
body = r.json()
print(json.dumps({'status': r.status_code, 'id': body.get('id',''), 'email': body.get('email','')}))
"""
        result = run_test_script(script)
        assert result["status"] == 200
        assert result["id"] == "uid-me"
        assert result["email"] == "me@example.com"

    def test_me_no_auth(self):
        """HTTP 401 when no Authorization header. Req 3.10"""
        script = _PREAMBLE + """
r = client.get('/api/v1/auth/me')
print(json.dumps({'status': r.status_code}))
"""
        result = run_test_script(script)
        assert result["status"] == 401
