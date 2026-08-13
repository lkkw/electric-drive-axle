from desktop import HOST, reserve_local_port


def test_reserve_local_port_uses_loopback_and_os_assigned_port() -> None:
    listener, port = reserve_local_port()

    try:
        host, bound_port = listener.getsockname()
        assert host == HOST
        assert port == bound_port
        assert port > 0
    finally:
        listener.close()
