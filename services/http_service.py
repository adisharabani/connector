import requests
from .service import Service
from .connector import Connector
from logger import get_logger
from threading import Thread
logger = get_logger(__name__)

class HTTPRequestConnector(Connector):
    def __init__(self, url, method: str = "GET", headers: dict = None, body: str = None, debug=False):
        super().__init__()  # Initialize with no value
        self.url = url
        self.method = method.upper()
        self.headers = headers or {}
        self.body = body
        self.debug = debug
        logger.info(f"Created HTTPRequestConnector for {self.method} {self.url}")

    def _set_action(self, value):
        Thread(target=lambda: self.send(value)).start()

    def send(self, value):
        try:
            if self.debug: logger.info(f"Sending HTTP {self.method} to {self.url} with data: {value}")
            response = requests.request(
                self.method,
                self.url,
                headers=self.headers,
                data=value
            )
            if self.debug: logger.info(f"HTTP response: {response.status_code} {response.text}")
        except Exception as e:
            logger.error(f"HTTP request failed: {e}")

class HTTP(Service):
    def __init__(self,debug=False):
        super().__init__()
        self.debug = debug

    def device(self, url, method: str = "GET", headers: dict = None, body: str = None) -> Connector:
        """
        Returns a Connector. When set, it sends the HTTP request.
        If dynamic_body is True, the value set is used as the request body.
        """
        return HTTPRequestConnector(url, method=method, headers=headers, body=body, debug=self.debug)
        
