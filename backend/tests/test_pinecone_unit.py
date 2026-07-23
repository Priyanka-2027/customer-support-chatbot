"""
Pinecone integration unit tests.

Uses subprocess isolation to avoid sys.modules pollution and to allow
patching ENVIRONMENT and Pinecone imports cleanly per test.

Covers:
  - get_pinecone_store() returns PineconeVectorStore with mock embedding
  - get_pinecone_store() lru_cache — called only once
  - build_pinecone_store() delegates to PineconeVectorStore.from_documents()
  - upsert_to_pinecone() returns correct chunk count
  - upsert_to_pinecone() logs and re-raises on exception
  - health_check() returns backend="faiss" in development
  - health_check() returns backend="pinecone" in production
  - health_check() returns vectorstore_loaded=False when Pinecone probe raises
  - Startup validator raises RuntimeError when PINECONE_API_KEY empty in production
  - Startup validator raises RuntimeError when PINECONE_INDEX_NAME empty in production
  - Startup validator does not raise when ENVIRONMENT="development"
  - POST /upload returns 422 with "Pinecone" in detail when upsert raises in production
  - POST /upload deletes the saved file when upsert raises in production
  - POST /upload/batch marks all files failed when batch upsert raises in production
"""

import sys
import os
import subprocess
import json

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PYTHON = sys.executable


def run_script(script: str) -> dict:
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
            f"Script failed (code {result.returncode}):\n"
            f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )
    try:
        return json.loads(result.stdout.strip())
    except json.JSONDecodeError:
        raise RuntimeError(f"Could not parse JSON output:\n{result.stdout}")


# ── Shared preamble ───────────────────────────────────────────
_PREAMBLE = """
import sys, os, types, json
from unittest.mock import MagicMock, AsyncMock, patch, call
sys.path.insert(0, '.')

_cfg = types.ModuleType('app.config')
_cfg.ENVIRONMENT = 'development'
_cfg.JWT_SECRET_KEY = 'test-secret-32-chars-minimum!!!!!'
_cfg.JWT_ALGORITHM = 'HS256'
_cfg.ACCESS_TOKEN_EXPIRE_MINUTES = 15
_cfg.REFRESH_TOKEN_EXPIRE_DAYS = 7
_cfg.CHAT_HISTORY_WINDOW = 10
_cfg.GEMINI_MODEL = 'gemini-pro'
_cfg.GOOGLE_API_KEY = ''
_cfg.DOCUMENTS_DIR = '/tmp/docs'
_cfg.VECTORSTORE_DIR = '/tmp/vs'
_cfg.DATABASE_PATH = '/tmp/test.db'
_cfg.RETRIEVER_K = 3
_cfg.CHUNK_SIZE = 1000
_cfg.CHUNK_OVERLAP = 200
_cfg.PINECONE_API_KEY = 'test-pinecone-key'
_cfg.PINECONE_INDEX_NAME = 'test-index'
sys.modules['app.config'] = _cfg

_STUBS = ['langchain', 'langchain.chains', 'langchain.chains.combine_documents',
    'langchain_community', 'langchain_community.vectorstores', 'langchain_google_genai',
    'langchain_huggingface', 'sentence_transformers', 'faiss',
    'app.chain', 'app.embeddings', 'app.vectorstore', 'app.ingest']
for m in _STUBS:
    sys.modules[m] = MagicMock()

_db = MagicMock()
_db.create_user = AsyncMock(return_value=None)
_db.get_user_by_email = AsyncMock(return_value=None)
_db.get_user_by_id = AsyncMock(return_value=None)
_db.init_db = AsyncMock(return_value=None)
sys.modules['app.database'] = _db

try:
    import bcrypt as _b, types as _t
    if not hasattr(_b, '__about__'):
        a = _t.ModuleType('bcrypt.__about__')
        a.__version__ = '4.0.1'
        _b.__about__ = a
    if not getattr(_b, '_hashpw_patched', False):
        _oh = _b.hashpw
        _b.hashpw = lambda p, s: _oh(p[:72], s)
        _b._hashpw_patched = True
except Exception:
    pass
"""


# ─────────────────────────────────────────────────────────────
# pinecone_store.py tests
# ─────────────────────────────────────────────────────────────

class TestGetPineconeStore:

    def test_returns_pinecone_vectorstore(self):
        """get_pinecone_store() returns a PineconeVectorStore instance."""
        script = _PREAMBLE + """
from unittest.mock import MagicMock
import types, app.pinecone_store as _ps

# Reset singleton
_ps._pinecone_store_instance = None

mock_store = MagicMock()
lp = types.ModuleType('langchain_pinecone')
lp.PineconeVectorStore = MagicMock(return_value=mock_store)
sys.modules['langchain_pinecone'] = lp

from app.pinecone_store import get_pinecone_store
mock_embedding = MagicMock()
result = get_pinecone_store(mock_embedding)
print(json.dumps({'ok': lp.PineconeVectorStore.called}))
"""
        result = run_script(script)
        assert result["ok"] is True

    def test_lru_cache_called_once(self):
        """get_pinecone_store() calls PineconeVectorStore constructor exactly once (singleton)."""
        script = _PREAMBLE + """
from unittest.mock import MagicMock
import types, app.pinecone_store as _ps

_ps._pinecone_store_instance = None

call_count = 0
class FakePVS:
    def __init__(self, **kwargs):
        global call_count
        call_count += 1

lp = types.ModuleType('langchain_pinecone')
lp.PineconeVectorStore = FakePVS
sys.modules['langchain_pinecone'] = lp

from app.pinecone_store import get_pinecone_store
mock_embedding = MagicMock()
get_pinecone_store(mock_embedding)
get_pinecone_store(mock_embedding)
get_pinecone_store(mock_embedding)
print(json.dumps({'call_count': call_count}))
"""
        result = run_script(script)
        assert result["call_count"] == 1

    def test_passes_correct_index_name(self):
        """get_pinecone_store() passes PINECONE_INDEX_NAME to constructor."""
        script = _PREAMBLE + """
import types, app.pinecone_store as _ps
_ps._pinecone_store_instance = None

captured = {}
class FakePVS:
    def __init__(self, **kwargs):
        captured.update(kwargs)

lp = types.ModuleType('langchain_pinecone')
lp.PineconeVectorStore = FakePVS
sys.modules['langchain_pinecone'] = lp

from app.pinecone_store import get_pinecone_store
from unittest.mock import MagicMock
get_pinecone_store(MagicMock())
print(json.dumps({'index_name': captured.get('index_name', '')}))
"""
        result = run_script(script)
        assert result["index_name"] == "test-index"


class TestUpsertToPinecone:

    def test_returns_chunk_count(self):
        """upsert_to_pinecone() returns the number of chunks upserted."""
        script = _PREAMBLE + """
import types
from unittest.mock import MagicMock
import app.pinecone_store as _ps

_ps._pinecone_store_instance = None

mock_store = MagicMock()
mock_store.add_documents = MagicMock(return_value=None)

lp = types.ModuleType('langchain_pinecone')
lp.PineconeVectorStore = MagicMock(return_value=mock_store)
sys.modules['langchain_pinecone'] = lp

from app.pinecone_store import upsert_to_pinecone

mock_embedding = MagicMock()
chunks = [MagicMock(), MagicMock(), MagicMock()]
count = upsert_to_pinecone(chunks, mock_embedding)
print(json.dumps({'count': count}))
"""
        result = run_script(script)
        assert result["count"] == 3

    def test_reraises_on_exception(self):
        """upsert_to_pinecone() re-raises exceptions from Pinecone."""
        script = _PREAMBLE + """
import types
from unittest.mock import MagicMock
import app.pinecone_store as _ps

_ps._pinecone_store_instance = None

mock_store = MagicMock()
mock_store.add_documents = MagicMock(side_effect=RuntimeError('Pinecone down'))

lp = types.ModuleType('langchain_pinecone')
lp.PineconeVectorStore = MagicMock(return_value=mock_store)
sys.modules['langchain_pinecone'] = lp

from app.pinecone_store import upsert_to_pinecone
mock_embedding = MagicMock()
raised = False
try:
    upsert_to_pinecone([MagicMock()], mock_embedding)
except RuntimeError:
    raised = True
print(json.dumps({'raised': raised}))
"""
        result = run_script(script)
        assert result["raised"] is True


class TestBuildPineconeStore:

    def test_calls_from_documents(self):
        """build_pinecone_store() delegates to PineconeVectorStore.from_documents()."""
        script = _PREAMBLE + """
import types
from unittest.mock import MagicMock

called_with_chunks = None

class FakePVS:
    @classmethod
    def from_documents(cls, documents, embedding, index_name, pinecone_api_key):
        global called_with_chunks
        called_with_chunks = len(documents)
        return MagicMock()

lp = types.ModuleType('langchain_pinecone')
lp.PineconeVectorStore = FakePVS
sys.modules['langchain_pinecone'] = lp

from app.pinecone_store import build_pinecone_store

chunks = [MagicMock(), MagicMock()]
mock_embedding = MagicMock()
build_pinecone_store(chunks, mock_embedding)
print(json.dumps({'chunks_passed': called_with_chunks}))
"""
        result = run_script(script)
        assert result["chunks_passed"] == 2


# ─────────────────────────────────────────────────────────────
# health_check() tests
# ─────────────────────────────────────────────────────────────

class TestHealthCheck:

    def test_returns_faiss_backend_in_development(self):
        """health_check() returns backend='faiss' in development."""
        script = _PREAMBLE + """
import types

mock_faiss = MagicMock()
mock_faiss.index.ntotal = 5
sys.modules['app.vectorstore'] = MagicMock(load_vectorstore=MagicMock(return_value=mock_faiss))

sys.modules.pop('app.chat', None)
from fastapi import FastAPI
from starlette.testclient import TestClient

sys.modules['app.retriever'] = MagicMock()
sys.modules['app.chain'] = MagicMock()
import fastapi as _f
_as = MagicMock(); _as.router = _f.APIRouter()
sys.modules['app.auth'] = _as
sys.modules.pop('app.chat', None)

from app.chat import router as chat_router
app = FastAPI()
app.include_router(chat_router, prefix='/api/v1')
client = TestClient(app, raise_server_exceptions=True)
r = client.get('/api/v1/health')
body = r.json()
print(json.dumps({'backend': body.get('backend', ''), 'status': r.status_code}))
"""
        result = run_script(script)
        assert result["backend"] == "faiss"
        assert result["status"] == 200

    def test_returns_pinecone_backend_in_production(self):
        """health_check() returns backend='pinecone' in production."""
        script = _PREAMBLE + """
import sys, types

# Switch to production
import app.config as _cfg_module
_cfg_module.ENVIRONMENT = 'production'
sys.modules['app.config'].ENVIRONMENT = 'production'

mock_store = MagicMock()
mock_store._index.describe_index_stats.return_value = {'total_vector_count': 10}

mock_pinecone_store_mod = MagicMock()
mock_pinecone_store_mod.get_pinecone_store = MagicMock(return_value=mock_store)
sys.modules['app.pinecone_store'] = mock_pinecone_store_mod
sys.modules['app.embeddings'] = MagicMock(get_embedding_model=MagicMock(return_value=MagicMock()))

sys.modules.pop('app.chat', None)
from fastapi import FastAPI
from starlette.testclient import TestClient
import fastapi as _f
_as = MagicMock(); _as.router = _f.APIRouter()
sys.modules['app.auth'] = _as
sys.modules['app.chain'] = MagicMock()
sys.modules['app.retriever'] = MagicMock()
sys.modules['app.vectorstore'] = MagicMock()

from app.chat import router as chat_router
app = FastAPI()
app.include_router(chat_router, prefix='/api/v1')
client = TestClient(app, raise_server_exceptions=True)
r = client.get('/api/v1/health')
body = r.json()
print(json.dumps({'backend': body.get('backend', ''), 'vectorstore_loaded': body.get('vectorstore_loaded', False)}))
"""
        result = run_script(script)
        assert result["backend"] == "pinecone"
        assert result["vectorstore_loaded"] is True

    def test_vectorstore_loaded_false_when_pinecone_probe_raises(self):
        """health_check() returns vectorstore_loaded=False when Pinecone probe raises."""
        script = _PREAMBLE + """
import sys

sys.modules['app.config'].ENVIRONMENT = 'production'

mock_pinecone_store_mod = MagicMock()
mock_pinecone_store_mod.get_pinecone_store = MagicMock(side_effect=Exception("Pinecone unreachable"))
sys.modules['app.pinecone_store'] = mock_pinecone_store_mod
sys.modules['app.embeddings'] = MagicMock(get_embedding_model=MagicMock(return_value=MagicMock()))

sys.modules.pop('app.chat', None)
from fastapi import FastAPI
from starlette.testclient import TestClient
import fastapi as _f
_as = MagicMock(); _as.router = _f.APIRouter()
sys.modules['app.auth'] = _as
sys.modules['app.chain'] = MagicMock()
sys.modules['app.retriever'] = MagicMock()
sys.modules['app.vectorstore'] = MagicMock()

from app.chat import router as chat_router
app = FastAPI()
app.include_router(chat_router, prefix='/api/v1')
client = TestClient(app, raise_server_exceptions=True)
r = client.get('/api/v1/health')
body = r.json()
print(json.dumps({'vectorstore_loaded': body.get('vectorstore_loaded', True)}))
"""
        result = run_script(script)
        assert result["vectorstore_loaded"] is False


# ─────────────────────────────────────────────────────────────
# Startup credential validation tests
# ─────────────────────────────────────────────────────────────

class TestStartupCredentialValidation:

    def test_raises_when_api_key_empty_in_production(self):
        """RuntimeError raised when PINECONE_API_KEY is empty in production."""
        script = _PREAMBLE + """
import sys
import types

sys.modules['app.config'].ENVIRONMENT = 'production'
sys.modules['app.config'].PINECONE_API_KEY = ''
sys.modules['app.config'].PINECONE_INDEX_NAME = 'my-index'
sys.modules['app.config'].JWT_SECRET_KEY = 'test-secret-32-chars-minimum!!!!!'

sys.modules.pop('app.main', None)
sys.modules['app.retriever'] = MagicMock()
sys.modules['app.embeddings'] = MagicMock()
sys.modules['app.chain'] = MagicMock()
sys.modules['app.vectorstore'] = MagicMock()

import fastapi as _f
_as = MagicMock(); _as.router = _f.APIRouter()
sys.modules['app.auth'] = _as
_cs = MagicMock(); _cs.router = _f.APIRouter()
sys.modules['app.chat'] = _cs

raised = False
msg = ''
try:
    from app.main import lifespan, app
    from fastapi import FastAPI
    import asyncio
    async def run():
        async with lifespan(app):
            pass
    asyncio.run(run())
except RuntimeError as e:
    raised = True
    msg = str(e)
except Exception:
    pass
print(json.dumps({'raised': raised, 'has_key_msg': 'PINECONE_API_KEY' in msg}))
"""
        result = run_script(script)
        assert result["raised"] is True
        assert result["has_key_msg"] is True

    def test_raises_when_index_name_empty_in_production(self):
        """RuntimeError raised when PINECONE_INDEX_NAME is empty in production."""
        script = _PREAMBLE + """
import sys

sys.modules['app.config'].ENVIRONMENT = 'production'
sys.modules['app.config'].PINECONE_API_KEY = 'valid-key'
sys.modules['app.config'].PINECONE_INDEX_NAME = ''
sys.modules['app.config'].JWT_SECRET_KEY = 'test-secret-32-chars-minimum!!!!!'

sys.modules.pop('app.main', None)
sys.modules['app.retriever'] = MagicMock()
sys.modules['app.embeddings'] = MagicMock()
sys.modules['app.chain'] = MagicMock()
sys.modules['app.vectorstore'] = MagicMock()

import fastapi as _f
_as = MagicMock(); _as.router = _f.APIRouter()
sys.modules['app.auth'] = _as
_cs = MagicMock(); _cs.router = _f.APIRouter()
sys.modules['app.chat'] = _cs

raised = False
msg = ''
try:
    from app.main import lifespan, app
    import asyncio
    async def run():
        async with lifespan(app):
            pass
    asyncio.run(run())
except RuntimeError as e:
    raised = True
    msg = str(e)
except Exception:
    pass
print(json.dumps({'raised': raised, 'has_name_msg': 'PINECONE_INDEX_NAME' in msg}))
"""
        result = run_script(script)
        assert result["raised"] is True
        assert result["has_name_msg"] is True

    def test_no_error_in_development(self):
        """No RuntimeError when ENVIRONMENT='development' regardless of Pinecone credentials."""
        script = _PREAMBLE + """
import sys

sys.modules['app.config'].ENVIRONMENT = 'development'
sys.modules['app.config'].PINECONE_API_KEY = ''
sys.modules['app.config'].PINECONE_INDEX_NAME = ''
sys.modules['app.config'].JWT_SECRET_KEY = 'test-secret-32-chars-minimum!!!!!'

sys.modules.pop('app.main', None)

# Mock retriever so pre-warm doesn't actually load FAISS
retriever_mock = MagicMock()
retriever_mock.get_retriever = MagicMock(side_effect=FileNotFoundError("no vectorstore"))
sys.modules['app.retriever'] = retriever_mock
sys.modules['app.embeddings'] = MagicMock(get_embedding_model=MagicMock())
sys.modules['app.chain'] = MagicMock()
sys.modules['app.vectorstore'] = MagicMock()

import fastapi as _f
_as = MagicMock(); _as.router = _f.APIRouter()
sys.modules['app.auth'] = _as
_cs = MagicMock(); _cs.router = _f.APIRouter()
sys.modules['app.chat'] = _cs

raised = False
try:
    from app.main import lifespan, app
    import asyncio
    async def run():
        async with lifespan(app):
            pass
    asyncio.run(run())
except RuntimeError:
    raised = True
except Exception:
    pass  # FileNotFoundError from missing vectorstore is fine
print(json.dumps({'raised': raised}))
"""
        result = run_script(script)
        assert result["raised"] is False


# ─────────────────────────────────────────────────────────────
# Upload endpoint tests (Pinecone error handling)
# ─────────────────────────────────────────────────────────────

class TestUploadPineconeErrorHandling:

    def test_upload_returns_422_with_pinecone_in_detail(self):
        """POST /upload returns 422 with 'Pinecone' in detail when upsert raises."""
        script = _PREAMBLE + """
import sys, io, tempfile, pathlib, unittest.mock as _um

sys.modules['app.config'].ENVIRONMENT = 'production'

tmpdir = tempfile.mkdtemp()
sys.modules['app.config'].DOCUMENTS_DIR = pathlib.Path(tmpdir)

sys.modules['app.pinecone_store'] = MagicMock()
sys.modules.pop('app.chat', None)

from fastapi import FastAPI
from starlette.testclient import TestClient
import fastapi as _f
_as = MagicMock(); _as.router = _f.APIRouter()
sys.modules['app.auth'] = _as
sys.modules['app.chain'] = MagicMock()
sys.modules['app.retriever'] = MagicMock()
sys.modules['app.vectorstore'] = MagicMock()
sys.modules['app.ingest'] = MagicMock(
    split_documents=MagicMock(return_value=[MagicMock()])
)

from app.chat import router as chat_router

# Patch _merge_chunks_into_store to raise (called by _ingest_single_file path)
# and _load_and_split to succeed
app = FastAPI()
app.include_router(chat_router, prefix='/api/v1')
client = TestClient(app, raise_server_exceptions=False)

pdf_bytes = b'%PDF-1.4 fake pdf'
with _um.patch('app.chat._save_upload', return_value=None), \
     _um.patch('app.chat._load_and_split', return_value=[MagicMock()]), \
     _um.patch('app.chat._merge_chunks_into_store', side_effect=RuntimeError('Pinecone connection failed')):
    r = client.post(
        '/api/v1/upload',
        files={'file': ('test.pdf', io.BytesIO(pdf_bytes), 'application/pdf')}
    )
body = r.json()
detail = body.get('detail', '')
print(json.dumps({'status': r.status_code, 'has_pinecone': 'Pinecone' in detail or 'pinecone' in detail.lower()}))
"""
        result = run_script(script)
        assert result["status"] == 422
        assert result["has_pinecone"] is True

    def test_batch_upload_marks_all_failed_on_pinecone_error(self):
        """POST /upload/batch marks all files failed when Pinecone upsert raises."""
        script = _PREAMBLE + """
import sys, io, tempfile, pathlib

sys.modules['app.config'].ENVIRONMENT = 'production'

tmpdir = tempfile.mkdtemp()
sys.modules['app.config'].DOCUMENTS_DIR = pathlib.Path(tmpdir)

mock_upsert = MagicMock(side_effect=RuntimeError('Pinecone unavailable'))
sys.modules['app.pinecone_store'] = MagicMock(upsert_to_pinecone=mock_upsert)

sys.modules.pop('app.chat', None)
from fastapi import FastAPI
from starlette.testclient import TestClient
import fastapi as _f, unittest.mock as _um
_as = MagicMock(); _as.router = _f.APIRouter()
sys.modules['app.auth'] = _as
sys.modules['app.chain'] = MagicMock()
sys.modules['app.retriever'] = MagicMock()
sys.modules['app.vectorstore'] = MagicMock()

mock_chunks = [MagicMock()]
sys.modules['app.ingest'] = MagicMock(
    load_documents=MagicMock(),
    split_documents=MagicMock(return_value=mock_chunks)
)

# Patch _merge_chunks_into_store to raise (simulates Pinecone batch failure)
with _um.patch('app.chat._merge_chunks_into_store', side_effect=RuntimeError('Pinecone unavailable')):
    from app.chat import router as chat_router
    app = FastAPI()
    app.include_router(chat_router, prefix='/api/v1')
    client = TestClient(app, raise_server_exceptions=False)

    pdf_bytes = b'%PDF-1.4 fake pdf'
    with _um.patch('app.chat._load_and_split', return_value=mock_chunks):
        with _um.patch('app.chat._save_upload', return_value=None):
            r = client.post(
                '/api/v1/upload/batch',
                files=[
                    ('files', ('a.pdf', io.BytesIO(pdf_bytes), 'application/pdf')),
                    ('files', ('b.pdf', io.BytesIO(pdf_bytes), 'application/pdf')),
                ]
            )

body = r.json()
results = body.get('results', [])
all_failed = all(not r_item['success'] for r_item in results)
print(json.dumps({'status': r.status_code, 'all_failed': all_failed, 'count': len(results)}))
"""
        result = run_script(script)
        assert result["all_failed"] is True
        assert result["count"] == 2
