# -*- coding: utf-8 -*-
"""百度翻译 API 客户端。

与旧实现的差异：

* ``https`` 替代 ``http``：旧版把 appkey 和签名放在明文 HTTP 的 URL 上裸奔。
* ``data=`` 替代 ``params=``：旧版声明 ``x-www-form-urlencoded`` 却把参数塞进
  query string，代理日志里全是密钥。
* 复用 ``requests.Session``：旧版每段一次 TLS 握手。
* 指数退避 + 抖动替代固定 ``sleep(1)``；命中 54003（限流）时自动降低速率并
  长期记住，避免反复触发。
* 失败抛异常，不再返回「含『错误』二字的字符串」。
"""

import random
import secrets
import time
from hashlib import md5

import requests

from .errors import Cancelled, ConfigError, TranslationError
from .segmenter import byte_len

ENDPOINT = 'https://fanyi-api.baidu.com/api/trans/vip/translate'

ERROR_MESSAGES = {
    '52001': '请求超时',
    '52002': '系统错误',
    '52003': '未授权用户，请检查 APPID',
    '54000': '必填参数为空',
    '54001': '签名错误，请检查 APPKEY',
    '54003': '访问频率受限，请降低并发',
    '54004': '账户余额不足',
    '54005': '长 query 请求频繁',
    '58000': '客户端 IP 非法',
    '58001': '译文语言方向不支持',
    '58002': '服务当前已关闭',
    '90107': '认证未通过或未生效',
}

#: 值得重试的错误码
RETRYABLE = frozenset({'52001', '52002', '54003', '54005'})

#: 触发限流的错误码，命中后降低请求速率
RATE_LIMIT = frozenset({'54003'})


class BaiduTranslator:
    """无状态翻译客户端，一次构造多次请求。"""

    def __init__(self, appid='', appkey='', *, timeout=20, max_retries=3):
        self.appid = (appid or '').strip()
        self.appkey = (appkey or '').strip()
        self.timeout = timeout
        self.max_retries = max_retries

        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'ArticleReducer/2.0',
        })

        #: 最小请求间隔（秒）。命中限流后自适应上调。
        self._min_interval = 0.0
        self._last_call = 0.0
        self._rate_limit_hits = 0

        #: 外部注入的取消判定，返回 True 则尽快抛出 Cancelled
        self.should_cancel = None

    # ── 凭证 ──────────────────────────────────────────────
    def has_credentials(self):
        return bool(self.appid and self.appkey)

    def update_credentials(self, appid, appkey):
        self.appid = (appid or '').strip()
        self.appkey = (appkey or '').strip()

    def _require_credentials(self):
        if not self.has_credentials():
            raise ConfigError('尚未配置 APPID / APPKEY，请先在左侧填写并保存。')

    # ── 取消 ──────────────────────────────────────────────
    def _check_cancel(self):
        if self.should_cancel is not None and self.should_cancel():
            raise Cancelled('已取消')

    def _sleep(self, seconds):
        """可被取消打断的等待。"""
        deadline = time.monotonic() + max(seconds, 0)
        while True:
            self._check_cancel()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(remaining, 0.1))

    def _pace(self):
        """保证两次请求之间不小于最小间隔。"""
        if self._min_interval > 0:
            elapsed = time.monotonic() - self._last_call
            if elapsed < self._min_interval:
                self._sleep(self._min_interval - elapsed)
        self._last_call = time.monotonic()

    def _backoff(self, attempt):
        delay = min(0.6 * (2 ** attempt), 6.0) + random.uniform(0, 0.3)
        return max(delay, self._min_interval)

    # ── 签名 ──────────────────────────────────────────────
    @staticmethod
    def _sign(appid, query, salt, appkey):
        return md5((appid + query + salt + appkey).encode('utf-8')).hexdigest()

    # ── 对外 ──────────────────────────────────────────────
    def translate(self, text, from_lang, to_lang):
        """翻译一段文本。

        Raises:
            ConfigError: 凭证缺失
            TranslationError: 服务端或网络错误
            Cancelled: 用户取消
        """
        if not text or not text.strip():
            return ''

        self._require_credentials()

        size = byte_len(text)
        if size > 5600:
            raise TranslationError(
                '单次请求 {} 字节，超过接口上限，分段逻辑有误'.format(size)
            )

        last_error = None
        for attempt in range(self.max_retries):
            self._check_cancel()
            self._pace()
            try:
                return self._request(text, from_lang, to_lang)
            except TranslationError as exc:
                last_error = exc
                if not exc.retryable:
                    raise
                if exc.code in RATE_LIMIT:
                    self._rate_limit_hits += 1
                    # 限流一次就把全局节奏放慢，避免整篇反复撞墙
                    self._min_interval = min(self._min_interval + 0.5, 3.0)
            except requests.RequestException as exc:
                last_error = TranslationError(
                    '网络请求失败：{}'.format(exc), retryable=True
                )

            if attempt < self.max_retries - 1:
                self._sleep(self._backoff(attempt))

        raise last_error or TranslationError('翻译失败，未知原因')

    def _request(self, text, from_lang, to_lang):
        salt = str(secrets.randbelow(2 ** 31))
        payload = {
            'appid': self.appid,
            'q': text,
            'from': from_lang,
            'to': to_lang,
            'salt': salt,
            'sign': self._sign(self.appid, text, salt, self.appkey),
        }

        response = self.session.post(ENDPOINT, data=payload, timeout=self.timeout)
        response.raise_for_status()

        try:
            data = response.json()
        except ValueError:
            raise TranslationError(
                '接口返回的不是合法 JSON（HTTP {}）'.format(response.status_code)
            )

        code = data.get('error_code')
        if code:
            message = ERROR_MESSAGES.get(str(code), data.get('error_msg', '未知错误'))
            raise TranslationError(
                '{}（错误码 {}）'.format(message, code),
                code=str(code),
                retryable=str(code) in RETRYABLE,
            )

        results = data.get('trans_result') or []
        if not results:
            raise TranslationError('接口未返回译文，可能是 {}-{} 语言方向不支持'.format(
                from_lang, to_lang))

        return ''.join(item.get('dst', '') for item in results)

    def close(self):
        self.session.close()
