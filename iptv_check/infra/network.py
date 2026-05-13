import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib3.exceptions import InsecureRequestWarning
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)


class HttpClient:
    def __init__(self, timeout_connect: int = 3, timeout_read: int = 8, max_retries: int = 3):
        self._session = requests.Session()
        adapter = HTTPAdapter(
            pool_connections=10,
            pool_maxsize=30,
            max_retries=Retry(total=max_retries, backoff_factor=1, status_forcelist=[502, 503, 504]),
        )
        self._session.mount("http://", adapter)
        self._session.mount("https://", adapter)
        self._timeout = (timeout_connect, timeout_read)
        self._default_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

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
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((requests.exceptions.RequestException,)),
        reraise=True,
    )
    def get_with_retry(self, url: str, timeout: int = 5, verify: bool = False, **kwargs) -> requests.Response:
        resp = self._session.get(url, timeout=timeout, verify=verify, headers=self._default_headers, **kwargs)
        resp.raise_for_status()
        return resp

    def close(self):
        self._session.close()
