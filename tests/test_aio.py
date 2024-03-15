import asyncio
import base64
import struct
from unittest.mock import patch

import pytest

import consul
import consul.aio

Check = consul.Check


@pytest.fixture()
async def consul_obj(consul_port):
    c = consul.aio.Consul(port=consul_port)
    yield c
    await c.close()


@pytest.fixture()
async def consul_acl_obj(acl_consul):
    c = consul.aio.Consul(port=acl_consul.port, token=acl_consul.token)
    yield c
    await c.close()


class TestAsyncioConsul:
    async def test_kv(self, consul_obj):
        c = consul_obj
        _index, data = await c.kv.get("foo")
        assert data is None
        response = await c.kv.put("foo", "bar")
        assert response is True
        _index, data = await c.kv.get("foo")
        assert data["Value"] == b"bar"

    async def test_consul_ctor(self, consul_obj):
        c = consul_obj
        await c.kv.put("foo", struct.pack("i", 1000))
        _index, data = await c.kv.get("foo")
        assert struct.unpack("i", data["Value"]) == (1000,)

    async def test_kv_binary(self, consul_obj):
        c = consul_obj
        await c.kv.put("foo", struct.pack("i", 1000))
        _index, data = await c.kv.get("foo")
        assert struct.unpack("i", data["Value"]) == (1000,)

    async def test_kv_missing(self, consul_obj):
        c = consul_obj

        async def put():
            await asyncio.sleep(2.0 / 100)
            await c.kv.put("foo", "bar")

        fut = asyncio.ensure_future(put())
        await c.kv.put("index", "bump")
        index, data = await c.kv.get("foo")
        assert data is None
        index, data = await c.kv.get("foo", index=index)
        assert data["Value"] == b"bar"
        await fut
        await c.close()

    async def test_kv_put_flags(self, consul_obj):
        c = consul_obj
        await c.kv.put("foo", "bar")
        _index, data = await c.kv.get("foo")
        assert data["Flags"] == 0

        response = await c.kv.put("foo", "bar", flags=50)
        assert response is True
        _index, data = await c.kv.get("foo")
        assert data["Flags"] == 50

    async def test_kv_delete(self, consul_obj):
        c = consul_obj
        await c.kv.put("foo1", "1")
        await c.kv.put("foo2", "2")
        await c.kv.put("foo3", "3")
        _index, data = await c.kv.get("foo", recurse=True)
        assert [x["Key"] for x in data] == ["foo1", "foo2", "foo3"]

        response = await c.kv.delete("foo2")
        assert response is True
        _index, data = await c.kv.get("foo", recurse=True)
        assert [x["Key"] for x in data] == ["foo1", "foo3"]
        response = await c.kv.delete("foo", recurse=True)
        assert response is True
        _index, data = await c.kv.get("foo", recurse=True)
        assert data is None

    async def test_kv_subscribe(self, consul_obj):
        c = consul_obj

        async def put():
            await asyncio.sleep(1.0 / 100)
            response = await c.kv.put("foo", "bar")
            assert response is True

        fut = asyncio.ensure_future(put())
        index, data = await c.kv.get("foo")
        assert data is None
        index, data = await c.kv.get("foo", index=index)
        assert data["Value"] == b"bar"
        await fut

    async def test_transaction(self, consul_obj):
        c = consul_obj
        value = base64.b64encode(b"1").decode("utf8")
        d = {"KV": {"Verb": "set", "Key": "asdf", "Value": value}}
        r = await c.txn.put([d])
        assert r["Errors"] is None

        d = {"KV": {"Verb": "get", "Key": "asdf"}}
        r = await c.txn.put([d])
        assert r["Results"][0]["KV"]["Value"] == value

    async def test_agent_services(self, consul_obj):
        c = consul_obj
        services = await c.agent.services()
        assert services == {}
        response = await c.agent.service.register("foo")
        assert response is True
        services = await c.agent.services()
        assert services == {
            "foo": {
                "Port": 0,
                "ID": "foo",
                "CreateIndex": 0,
                "ModifyIndex": 0,
                "EnableTagOverride": False,
                "Service": "foo",
                "Tags": [],
                "Meta": {},
                "Address": "",
            },
        }
        response = await c.agent.service.deregister("foo")
        assert response is True
        services = await c.agent.services()
        assert services == {}

    async def test_catalog(self, consul_obj):
        c = consul_obj

        async def register():
            await asyncio.sleep(1.0 / 100)
            response = await c.catalog.register("n1", "10.1.10.11")
            assert response is True
            await asyncio.sleep(50 / 1000.0)
            response = await c.catalog.deregister("n1")
            assert response is True

        fut = asyncio.ensure_future(register())
        index, nodes = await c.catalog.nodes()
        assert len(nodes) == 1
        current = nodes[0]

        index, nodes = await c.catalog.nodes(index=index)
        nodes.remove(current)
        assert [x["Node"] for x in nodes] == ["n1"]

        index, nodes = await c.catalog.nodes(index=index)
        nodes.remove(current)
        assert [x["Node"] for x in nodes] == []
        await fut

    async def test_session(self, consul_obj):
        c = consul_obj

        async def register():
            await asyncio.sleep(1.0 / 100)
            session_id = await c.session.create()
            await asyncio.sleep(50 / 1000.0)
            response = await c.session.destroy(session_id)
            assert response is True

        fut = asyncio.ensure_future(register())
        index, services = await c.session.list()
        assert services == []
        await asyncio.sleep(20 / 1000.0)

        index, services = await c.session.list(index=index)
        assert len(services)

        index, services = await c.session.list(index=index)
        assert services == []
        await fut

    async def test_acl(self, consul_acl_obj):
        c = consul_acl_obj

        rules = """
            key "" {
                policy = "read"
            }
            key "private/" {
                policy = "deny"
            }
        """

        token = await c.acl.create(rules=rules)

        with pytest.raises(consul.ACLPermissionDenied):
            await c.acl.list(token=token)

        destroyed = await c.acl.destroy(token)
        assert destroyed is True

    async def test_acl_token_header(self, consul_acl_obj):
        c = consul_acl_obj

        rules = """
            key "" {
                policy = "read"
            }
            key "private/" {
                policy = "deny"
            }
        """

        token = await c.acl.create(rules=rules)

        # Wrap the underlying session.request method
        with patch.object(
            c.http._session, "request", wraps=c.http._session.request  # pylint: disable=protected-access
        ) as mock_request:
            with pytest.raises(consul.ACLPermissionDenied):
                await c.acl.list(token=token)

            # Ensure the mocked method was called
            assert mock_request.called

            # Extract the called arguments
            called_uri = mock_request.call_args.args[1]

            # Assert token is not in the URL
            assert f"token={token}" not in called_uri

            # Assert the X-Consul-Token header is present
            called_headers = mock_request.call_args.kwargs["headers"]
            assert "X-Consul-Token" in called_headers
            assert called_headers["X-Consul-Token"] == token

        destroyed = await c.acl.destroy(token)
        assert destroyed is True
