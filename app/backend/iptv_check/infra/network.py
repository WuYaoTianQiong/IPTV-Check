import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib3.exceptions import InsecureRequestWarning
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, before_sleep_log
from pybreaker import CircuitBreaker

from iptv_check.infra.config.settings import settings

logger = logging.getLogger(__name__)

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)


class ResilientHttpClient:
    def __init__(self):
        self._session = requests.Session()
        adapter = HTTPAdapter(
            pool_connections=settings.http_pool_connections,
            pool_maxsize=settings.http_pool_maxsize,
            max_retries=Retry(
                total=settings.http_max_retries,
                backoff_factor=1,
                status_forcelist=[502, 503, 504],
            ),
        )
        self._session.mount("http://", adapter)
        self._session.mount("https://", adapter)
        self._timeout = (settings.check_timeout_connect, settings.check_timeout_read)
        self._default_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        self._download_breaker = CircuitBreaker(
            fail_max=settings.breaker_fail_max,
            reset_timeout=settings.breaker_reset_timeout,
        )

    def update_timeout(self, timeout_connect: int, timeout_read: int):
        self._timeout = (timeout_connect, timeout_read)

    def get(self, url: str, headers: dict = None, timeout: tuple = None,
            stream: bool = False, verify: bool = True, **kwargs) -> requests.Response:
        kwargs.setdefault("timeout", timeout or self._timeout)
        kwargs.setdefault("headers", headers or self._default_headers)
        kwargs.setdefault("verify", verify)
        kwargs.setdefault("stream", stream)
        kwargs.setdefault("allow_redirects", True)
        return self._session.get(url, **kwargs)

    def get_unsafe(self, url: str, **kwargs) -> requests.Response:
        kwargs["verify"] = False
        return self.get(url, **kwargs)

    @retry(
        stop=stop_after_attempt(settings.download_retries),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((requests.exceptions.Timeout, requests.exceptions.ConnectionError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def get_with_retry(self, url: str, timeout: int = None, verify: bool = False, **kwargs) -> requests.Response:
        resp = self._session.get(url, timeout=timeout or settings.download_timeout, verify=verify, headers=self._default_headers, **kwargs)
        resp.raise_for_status()
        return resp

    def get_with_breaker(self, url: str, **kwargs) -> requests.Response:
        return self._download_breaker.call(self.get, url, **kwargs)

    @property
    def breaker_state(self) -> str:
        if self._download_breaker.current_state == "closed":
            return "normal"
        if self._download_breaker.current_state == "open":
            return "tripped"
        return "half_open"

    def close(self):
        self._session.close()


class HttpClient(ResilientHttpClient):
    pass
