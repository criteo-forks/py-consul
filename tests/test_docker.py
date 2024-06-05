def test_kv_recurse(fresh_consul_admin):
    c = fresh_consul_admin
    _index, data = c.kv.get("foo/", recurse=True)
    assert data is None

    c.kv.put("foo/", None)
    _index, data = c.kv.get("foo/", recurse=True)
    assert len(data) == 1

    c.kv.put("foo/bar1", "1")
    c.kv.put("foo/bar2", "2")
    c.kv.put("foo/bar3", "3")
    _index, data = c.kv.get("foo/", recurse=True)
    assert [x["Key"] for x in data] == ["foo/", "foo/bar1", "foo/bar2", "foo/bar3"]
    assert [x["Value"] for x in data] == [None, b"1", b"2", b"3"]
