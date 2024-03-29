import base64
import json

from consul.exceptions import ACLDisabled, ACLPermissionDenied, BadRequest, ClientError, ConsulException, NotFound

#
# Conveniences to create consistent callback handlers for endpoints


class CB:
    @classmethod
    def _status(cls, response, allow_404=True):
        # status checking
        if 400 <= response.code < 500:
            if response.code == 400:
                raise BadRequest(f"{response.code} {response.body}")
            if response.code == 401:
                raise ACLDisabled(response.body)
            if response.code == 403:
                raise ACLPermissionDenied(response.body)
            if response.code == 404:
                if not allow_404:
                    raise NotFound(response.body)
            else:
                raise ClientError(f"{response.code} {response.body}")
        elif 500 <= response.code < 600:
            raise ConsulException(f"{response.code} {response.body}")

    @classmethod
    def bool(cls):
        # returns True on successful response
        def cb(response):
            CB._status(response)
            return response.code == 200

        return cb

    @classmethod
    def json(cls, postprocess=None, allow_404=True, one=False, decode=False, is_id=False, index=False):
        """
        *postprocess* is a function to apply to the final result.

        *allow_404* if set, None will be returned on 404, instead of raising
        NotFound.

        *index* if set, a tuple of index, data will be returned.

        *one* returns only the first item of the list of items. empty lists are
        coerced to None.

        *decode* if specified this key will be base64 decoded.

        *is_id* only the 'ID' field of the json object will be returned.
        """

        def cb(response):
            CB._status(response, allow_404=allow_404)
            if response.code == 404:
                data = None
            else:
                data = json.loads(response.body)
                if decode:
                    for item in data:
                        if item.get(decode) is not None:
                            item[decode] = base64.b64decode(item[decode])
                if is_id:
                    data = data["ID"]
                if one:
                    if data == []:
                        data = None
                    if data is not None:
                        data = data[0]
                if postprocess:
                    data = postprocess(data)
            if index:
                return response.headers["X-Consul-Index"], data
            return data

        return cb