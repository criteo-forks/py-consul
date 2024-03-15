import asyncio

import aiohttp

from consul import base

__all__ = ["Consul"]


class HTTPClient(base.HTTPClient):
    """Asyncio adapter for python consul using aiohttp library"""

    def __init__(self, *args, loop=None, connections_limit=None, connections_timeout=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._loop = loop or asyncio.get_event_loop()
        connector_kwargs = {}
        if connections_limit:
            connector_kwargs["limit"] = connections_limit
        connector = aiohttp.TCPConnector(loop=self._loop, verify_ssl=self.verify, **connector_kwargs)
        session_kwargs = {}
        if connections_timeout:
            timeout = aiohttp.ClientTimeout(total=connections_timeout)
            session_kwargs["timeout"] = timeout

        header = self.build_header(**kwargs)
        if header:
            session_kwargs["headers"] = header
        self._session = aiohttp.ClientSession(connector=connector, **session_kwargs)

    async def _request(self, callback, method, uri, data=None, connections_timeout=None, **kwargs):
        session_kwargs = {}
        if connections_timeout:
            timeout = aiohttp.ClientTimeout(total=connections_timeout)
            session_kwargs["timeout"] = timeout

        header = self.build_header(**kwargs)
        if header:
            session_kwargs["headers"] = header

        resp = await self._session.request(method, uri, data=data, **session_kwargs)
        body = await resp.text(encoding="utf-8")
        if resp.status == 599:
            raise base.Timeout
        r = base.Response(resp.status, resp.headers, body)
        return callback(r)

    def get(self, callback, path, params=None, connections_timeout=None, **kwargs):
        uri = self.uri(path, params)
        header = self.build_header(**kwargs)
        if header:
            kwargs["headers"] = header
        return self._request(callback, "GET", uri, connections_timeout=connections_timeout, **kwargs)

    def put(self, callback, path, params=None, data="", connections_timeout=None, **kwargs):
        uri = self.uri(path, params)
        return self._request(callback, "PUT", uri, data=data, connections_timeout=connections_timeout, **kwargs)

    def delete(self, callback, path, params=None, connections_timeout=None, **kwargs):
        uri = self.uri(path, params)
        return self._request(callback, "DELETE", uri, connections_timeout=connections_timeout, **kwargs)

    def post(self, callback, path, params=None, data="", connections_timeout=None, **kwargs):
        uri = self.uri(path, params)
        return self._request(callback, "POST", uri, data=data, connections_timeout=connections_timeout, **kwargs)

    def close(self):
        return self._session.close()


class Consul(base.Consul):
    def __init__(self, *args, loop=None, connections_limit=None, connections_timeout=None, **kwargs):
        self._loop = loop or asyncio.get_event_loop()
        self.connections_limit = connections_limit
        self.connections_timeout = connections_timeout
        super().__init__(*args, **kwargs)

    def http_connect(self, host, port, scheme, verify=True, cert=None, **kwargs):
        return HTTPClient(
            host,
            port,
            scheme,
            loop=self._loop,
            connections_limit=self.connections_limit,
            connections_timeout=self.connections_timeout,
            verify=verify,
            cert=cert,
            **kwargs,
        )

    def close(self):
        """Close all opened http connections"""
        return self.http.close()
