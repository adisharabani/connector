import requests
from .service import Service
from .connector import Connector
from logger import get_logger

logger = get_logger(__name__)

class HTTPRequestConnector(Connector):
    def __init__(self, url, method: str = "GET", headers: dict = None, body: str = None):
        super().__init__()  # Initialize with no value
        self.url = url
        self.method = method.upper()
        self.headers = headers or {}
        self.body = body
        logger.info(f"Created HTTPRequestConnector for {self.method} {self.url}")

    def _set_action(self, value):
        try:
            logger.info(f"Sending HTTP {self.method} to {self.url} with body: {value}")
            response = requests.request(
                self.method,
                self.url,
                headers=self.headers,
                data=value
            )
            logger.info(f"HTTP response: {response.status_code} {response.text}")
        except Exception as e:
            logger.error(f"HTTP request failed: {e}")

class HTTP(Service):
    def __init__(self,debug=True):
        super().__init__()

    def device(self, url, method: str = "GET", headers: dict = None, body: str = None) -> Connector:
        """
        Returns a Connector. When set, it sends the HTTP request.
        If dynamic_body is True, the value set is used as the request body.
        """
        return HTTPRequestConnector(url, method=method, headers=headers, body=body)
        
