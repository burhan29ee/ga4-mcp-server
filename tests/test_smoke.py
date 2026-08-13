"""Smoke tests: the package imports and pure helpers work without credentials."""


def test_package_version():
    import ga4_mcp_server

    assert ga4_mcp_server.__version__


def test_server_and_entrypoint():
    from ga4_mcp_server import server

    assert callable(server.main)
    assert server.mcp is not None


def test_normalize_property_id():
    from ga4_mcp_server import server

    assert server._prop("123") == "properties/123"
    assert server._prop("properties/123") == "properties/123"
    assert server._prop("p123") == "properties/123"
