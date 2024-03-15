import requests

from consul import base

__all__ = ["Consul"]


class HTTPClient(base.HTTPClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session = requests.session()

    def response(self, response):
        response.encoding = "utf-8"
        return base.Response(response.status_code, response.headers, response.text)

    def get(self, callback, path, params=None, **kwargs):
        uri = self.uri(path, params)
        header = self.build_header(**kwargs)
        return callback(self.response(self.session.get(uri, verify=self.verify, cert=self.cert, headers=header)))

    def put(self, callback, path, params=None, data="", **kwargs):
        uri = self.uri(path, params)
        header = self.build_header(**kwargs)
        return callback(
            self.response(self.session.put(uri, data=data, verify=self.verify, cert=self.cert, headers=header))
        )

    def delete(self, callback, path, params=None, **kwargs):
        uri = self.uri(path, params)
        header = self.build_header(**kwargs)
        return callback(self.response(self.session.delete(uri, verify=self.verify, cert=self.cert, headers=header)))

    def post(self, callback, path, params=None, data="", **kwargs):
        uri = self.uri(path, params)
        header = self.build_header(**kwargs)
        return callback(
            self.response(self.session.post(uri, data=data, verify=self.verify, cert=self.cert, headers=header))
        )

    def close(self):
        pass


class Consul(base.Consul):
    def http_connect(self, host, port, scheme, verify=True, cert=None, **kwargs):
        return HTTPClient(host, port, scheme, verify, cert, **kwargs)
