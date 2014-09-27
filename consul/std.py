import urllib

import requests

from consul import base


__all__ = ['Consul']


class HTTPClient(object):
    def __init__(self, host='127.0.0.1', port=8500):
        self.host = host
        self.port = port
        self.base_uri = 'http://%s:%s' % (self.host, self.port)

    def response(self, response):
        return base.Response(
            response.status_code, response.headers, response.text)

    def uri(self, path, params=None):
        uri = self.base_uri + path
        if not params:
            return uri
        return '%s?%s' % (uri, urllib.urlencode(params))

    def get(self, callback, path, params=None):
        uri = self.uri(path, params)
        return callback(self.response(requests.get(uri)))

    def put(self, callback, path, params=None, data=''):
        uri = self.uri(path, params)
        return callback(self.response(requests.put(uri, data=data)))


class Consul(base.Consul):
    def connect(self, host, port):
        return HTTPClient(host, port)
