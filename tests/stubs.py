"""HTTP adapters that answer without touching the network."""

import requests
from requests.adapters import BaseAdapter
from requests.exceptions import RequestException
from requests.models import Response

DEFAULT_CONTENT = b'{"ok": true}'
DEFAULT_HEADERS = {"Content-Type": "application/json", "Set-Cookie": "session=secret"}


class StubAdapter(BaseAdapter):
    def __init__(self, status_code=200, content=DEFAULT_CONTENT, headers=None, error=None):
        super().__init__()
        self.status_code = status_code
        self.content = content
        self.headers = DEFAULT_HEADERS if headers is None else headers
        self.error = error
        self.received = []
        self.options = []

    def send(self, request, **kwargs):
        self.received.append(request)
        self.options.append(kwargs)
        if self.error:
            if issubclass(self.error, RequestException):
                raise self.error("the stub refused the connection", request=request)
            raise self.error("the stub broke before preparing anything")

        response = Response()
        response.status_code = self.status_code
        response.reason = "OK"
        response._content = self.content
        response.url = request.url
        response.request = request
        response.headers.update(self.headers)
        return response

    def close(self):
        pass


def build_stub_session():
    """What OUTBOUND_LOGGER["HTTP_SESSION_FACTORY"] points at in the tests:
    a session that carries credentials and never touches the network."""
    session = requests.Session()
    session.headers["Authorization"] = "Bearer the-real-one"
    session.mount("https://", StubAdapter())
    return session
