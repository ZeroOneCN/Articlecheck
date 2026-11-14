# -*- coding: utf-8 -*-
"""密钥安全存储。

旧版把 APPKEY 明文写进程序目录的 ``config.json``，任何进程都能读。

现在的降级链：
    1. ``keyring`` → Windows 凭据管理器（推荐，装了就用）
    2. Windows DPAPI → 绑定当前用户账户加密，无需额外依赖
    3. 都没有 → base64 混淆 + 标记 ``insecure``，界面上明示「未加密」

绝不假装第 3 步是加密。
"""

import base64
import ctypes
import sys
from ctypes import wintypes

SERVICE = 'ArticleReducer'
KEY_ACCOUNT = 'baidu-appkey'

# ── keyring ──────────────────────────────────────────────
try:
    import keyring
    _HAS_KEYRING = True
except Exception:                                       # pragma: no cover
    keyring = None
    _HAS_KEYRING = False


# ── Windows DPAPI ────────────────────────────────────────
class _Blob(ctypes.Structure):
    _fields_ = [
        ('cbData', wintypes.DWORD),
        ('pbData', ctypes.POINTER(ctypes.c_char)),
    ]


class _WindowsCrypto:
    """CryptProtectData / CryptUnprotectData 的最小封装。"""

    def __init__(self):
        self._crypt32 = ctypes.WinDLL('crypt32', use_last_error=True)
        self._kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

        self._crypt32.CryptProtectData.argtypes = [
            ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.c_void_p,
            ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
            ctypes.POINTER(_Blob),
        ]
        self._crypt32.CryptProtectData.restype = wintypes.BOOL
        self._crypt32.CryptUnprotectData.argtypes = [
            ctypes.POINTER(_Blob), ctypes.POINTER(ctypes.c_void_p),
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
            wintypes.DWORD, ctypes.POINTER(_Blob),
        ]
        self._crypt32.CryptUnprotectData.restype = wintypes.BOOL
        self._kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        self._kernel32.LocalFree.restype = ctypes.c_void_p

    @staticmethod
    def _make_blob(data):
        buf = ctypes.create_string_buffer(data, len(data))
        return _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf

    def protect(self, data):
        blob_in, _buf = self._make_blob(data)
        blob_out = _Blob()
        if not self._crypt32.CryptProtectData(
                ctypes.byref(blob_in), None, None, None, None, 0,
                ctypes.byref(blob_out)):
            raise OSError('CryptProtectData 失败，错误码 %s' % ctypes.get_last_error())
        try:
            return ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            self._kernel32.LocalFree(ctypes.cast(blob_out.pbData, ctypes.c_void_p))

    def unprotect(self, data):
        blob_in, _buf = self._make_blob(data)
        blob_out = _Blob()
        if not self._crypt32.CryptUnprotectData(
                ctypes.byref(blob_in), None, None, None, None, 0,
                ctypes.byref(blob_out)):
            raise OSError('CryptUnprotectData 失败，错误码 %s' % ctypes.get_last_error())
        try:
            return ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            self._kernel32.LocalFree(ctypes.cast(blob_out.pbData, ctypes.c_void_p))


_dpapi = None
_dpapi_ready = False
if __import__('sys').platform == 'win32':
    try:
        _dpapi = _WindowsCrypto()
        _dpapi_ready = True
    except Exception:                                   # pragma: no cover
        _dpapi_ready = False


# ── 对外接口 ─────────────────────────────────────────────
def backend_name():
    if _HAS_KEYRING:
        return 'keyring'
    if _dpapi_ready:
        return 'dpapi'
    return 'obfuscated'


def is_secure():
    return backend_name() != 'obfuscated'


def save_secret(value):
    """保存密钥，返回实际使用的后端名。"""
    if not value:
        return delete_secret()

    if _HAS_KEYRING:
        try:
            keyring.set_password(SERVICE, KEY_ACCOUNT, value)
            return 'keyring'
        except Exception:
            pass

    if _dpapi_ready:
        try:
            token = _dpapi.protect(value.encode('utf-8'))
            keyring_payload = 'dpapi:' + base64.b64encode(token).decode('ascii')
            _write_sidecar(keyring_payload)
            return 'dpapi'
        except Exception:
            pass

    _write_sidecar('b64:' + base64.b64encode(value.encode('utf-8')).decode('ascii'))
    return 'obfuscated'


def load_secret():
    """读取密钥，失败返回空串。"""
    if _HAS_KEYRING:
        try:
            value = keyring.get_password(SERVICE, KEY_ACCOUNT)
            if value:
                return value
        except Exception:
            pass

    payload = _read_sidecar()
    if not payload:
        return ''

    try:
        if payload.startswith('dpapi:') and _dpapi_ready:
            raw = base64.b64decode(payload[6:])
            return _dpapi.unprotect(raw).decode('utf-8')
        if payload.startswith('b64:'):
            return base64.b64decode(payload[4:]).decode('utf-8')
    except Exception:
        pass
    return ''


def delete_secret():
    if _HAS_KEYRING:
        try:
            keyring.delete_password(SERVICE, KEY_ACCOUNT)
        except Exception:
            pass
    _clear_sidecar()
    return backend_name()


# ── 降级时的落盘位置 ─────────────────────────────────────
def _sidecar_path():
    from .settings import config_dir
    return config_dir() / 'credential.dat'


def _write_sidecar(text):
    path = _sidecar_path()
    tmp = path.with_suffix('.tmp')
    tmp.write_text(text, encoding='ascii')
    tmp.replace(path)


def _read_sidecar():
    path = _sidecar_path()
    try:
        if path.exists():
            return path.read_text(encoding='ascii').strip()
    except Exception:
        pass
    return ''


def _clear_sidecar():
    path = _sidecar_path()
    try:
        if path.exists():
            path.unlink()
    except Exception:
        pass
