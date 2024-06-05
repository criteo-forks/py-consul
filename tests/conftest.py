import collections
import json
import os
import shlex
import socket
import subprocess
import tempfile
import time
import uuid

import pytest
import requests

from consul import Consul

collect_ignore = []

CONSUL_BINARIES = {
    "1.13.8": "consul-1.13.8",
    "1.15.4": "consul-1.15.4",
    "1.16.1": "consul-1.16.1",
    "1.17.3": "consul-1.17.3",
}

ACLConsul = collections.namedtuple("ACLConsul", ["instance", "token", "version"])


def get_free_ports(num, host=None):
    if not host:
        host = "127.0.0.1"
    sockets = []
    ret = []
    for _ in range(num):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind((host, 0))
        ret.append(s.getsockname()[1])
        sockets.append(s)
    for s in sockets:
        s.close()
    return ret


def start_consul_instance(binary_name, acl_master_token=None):
    """
    starts a consul instance. if acl_master_token is None, acl will be disabled
    for this server, otherwise it will be enabled and the master token will be
    set to the supplied token

    returns: a tuple of the instances process object and the http port the
             instance is listening on
    """
    ports = dict(zip(["http", "server", "grpc", "serf_lan", "serf_wan", "https", "dns"], get_free_ports(5) + [-1] * 2))
    if "1.13" not in binary_name:
        ports["grpc_tls"] = -1

    config = {"ports": ports, "performance": {"raft_multiplier": 1}, "enable_script_checks": True}
    if acl_master_token:
        config["primary_datacenter"] = "dc1"
        config["acl"] = {"enabled": True, "tokens": {"initial_management": acl_master_token}}

    tmpdir = tempfile.mkdtemp()
    config_path = os.path.join(tmpdir, "config.json")
    print(config_path)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

    ext = "linux64"
    binary = os.path.join(os.path.dirname(__file__), f"{binary_name}.{ext}")
    command = f"{binary} agent -dev -bind=127.0.0.1 -config-dir={tmpdir}"
    command = shlex.split(command)
    log_file_path = os.path.join(tmpdir, "consul.log")

    with open(log_file_path, "w", encoding="utf-8") as log_file:  # pylint: disable=unspecified-encoding
        p = subprocess.Popen(command, stdout=log_file, stderr=subprocess.STDOUT)  # pylint: disable=consider-using-with

    # wait for consul instance to bootstrap
    base_uri = f"http://127.0.0.1:{ports['http']}/v1/"
    start_time = time.time()
    global_timeout = 5

    while True:
        # Timeout at some point and read the log file to see what went wrong
        if time.time() - start_time > global_timeout:
            with open(log_file_path, encoding="utf-8") as log_file:
                print(log_file.read())
            raise TimeoutError("Global timeout reached")
        time.sleep(0.1)
        try:
            response = requests.get(base_uri + "status/leader", timeout=10)
        except requests.ConnectionError:
            continue
        print(response.text)
        if response.text.strip() != '""':
            break

    requests.put(base_uri + "agent/service/register", data='{"name": "foo"}', timeout=10)

    while True:
        response = requests.get(base_uri + "health/service/foo", timeout=10)
        if response.text.strip() != "[]":
            break
        time.sleep(0.1)

    requests.put(base_uri + "agent/service/deregister/foo", timeout=10)
    # phew
    time.sleep(2)
    return p, ports["http"]


def get_consul_version(port):
    base_uri = f"http://127.0.0.1:{port}/v1/"
    response = requests.get(base_uri + "agent/self", timeout=10)
    return response.json()["Config"]["Version"].strip()


@pytest.fixture(params=CONSUL_BINARIES.keys())
def consul_instance(request):
    p, port = start_consul_instance(binary_name=CONSUL_BINARIES[request.param])
    version = get_consul_version(port)
    yield port, version
    p.terminate()


@pytest.fixture(params=CONSUL_BINARIES.keys())
def acl_consul_instance(request):
    acl_master_token = uuid.uuid4().hex
    p, port = start_consul_instance(binary_name=CONSUL_BINARIES[request.param], acl_master_token=acl_master_token)
    version = get_consul_version(port)
    yield port, acl_master_token, version
    p.terminate()


@pytest.fixture()
def consul_port(consul_instance):
    port, version = consul_instance
    return port, version


@pytest.fixture()
def acl_consul(acl_consul_instance):
    consul_port, token, version = acl_consul_instance
    return ACLConsul(Consul(port=consul_port), token, version)


@pytest.fixture()
def consul_obj(consul_port):
    consul_port, consul_version = consul_port
    c = Consul(port=consul_port)
    return c, consul_version


@pytest.fixture(scope="session")
def fresh_consul_admin():
    # Wait for Consul to be up and running
    url = "http://localhost:8500/v1/status/leader"
    for _ in range(60):
        try:
            response = requests.get(url, timeout=2)
            if response.ok:
                break
        except requests.exceptions.ConnectionError:
            time.sleep(1)
    else:
        pytest.fail("Consul did not start within the expected time")

    c = Consul(port=8500, token="e95b599e-166e-7d80-08ad-aee76e7ddf19")
    yield c

    # Cleanup all keys in the KV store
    c.kv.delete("", recurse=True)
