"""HTTP adapters that answer without touching the network."""

from requests.adapters import BaseAdapter
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

    def send(self, request, **kwargs):
        self.received.append(request)
        if self.error:
            raise self.error("the stub refused the connection", request=request)

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
