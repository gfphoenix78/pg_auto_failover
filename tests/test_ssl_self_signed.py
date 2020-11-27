import pgautofailover_utils as pgautofailover

from nose.tools import eq_
from gp import *

import os.path

cluster = None
node1 = None
node2 = None


def setup_module():
    global cluster
    cluster = pgautofailover.Cluster()
    init_greenplum_env(cluster)


def teardown_module():
    destroy_gp_segments()
    cluster.destroy()


def test_000_create_monitor():
    monitor = cluster.create_monitor("/tmp/ssl-self-signed/monitor",
                                     sslSelfSigned=True)

    config_monitor(monitor)
    monitor.run()
    monitor.wait_until_pg_is_running()
    monitor.check_ssl("on", "require")


def test_001_init_primary():
    global node1
    config_master(cluster, '/tmp/ssl-self-signed/node1', 7000)
    node1 = cluster.create_datanode("/tmp/ssl-self-signed/node1",
                                    sslSelfSigned=True)
    node1.set_gp_params(gp_dbid = 1, port = 7000)
    node1.create()
    node1.run()
    assert node1.wait_until_state(target_state="single")

    node1.wait_until_pg_is_running()
    node1.check_ssl("on", "require", primary=True)


def test_002_create_t1():
    ops = set_utility(False)
    node1.run_sql_query("CREATE TABLE t1(a int)")
    node1.run_sql_query("INSERT INTO t1 VALUES (1), (2)")
    restore_utility(ops)


def test_003_init_secondary():
    global node2
    node2 = cluster.create_datanode("/tmp/ssl-self-signed/node2",
                                    sslSelfSigned=True,
                                    sslMode="require")
    node2.set_gp_params(gp_dbid = 8, port = 7001)

    node2.create()
    node2.run()
    config_standby(node1, node2)

    assert node2.wait_until_state(target_state="secondary")
    assert node1.wait_until_state(target_state="primary")

    node2.wait_until_pg_is_running()
    node2.check_ssl("on", "require")


def test_004_failover():
    print()
    print("Calling pgautofailover.failover() on the monitor")
    cluster.monitor.failover()
    assert node2.wait_until_state(target_state="primary")
    assert node1.wait_until_state(target_state="secondary")
