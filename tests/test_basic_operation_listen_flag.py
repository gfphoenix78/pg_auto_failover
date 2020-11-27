import pgautofailover_utils as pgautofailover
from nose.tools import *
from gp import *
import unittest

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
    monitor = cluster.create_monitor("/tmp/listen/monitor")
    config_monitor(monitor)
    monitor.run()

def test_001_init_primary():
    global node1
    config_master(cluster, '/tmp/listen/node1', 7000)
    node1 = cluster.create_datanode("/tmp/listen/node1", listen_flag=True)
    node1.set_gp_params(gp_dbid = 1, port = 7000)
    node1.create()
    node1.run()
    assert node1.wait_until_state(target_state="single")
    node1.wait_until_pg_is_running()

def test_002_create_t1():
    ops = set_utility(False)
    node1.run_sql_query("CREATE TABLE t1(a int)")
    node1.run_sql_query("INSERT INTO t1 VALUES (1), (2)")
    restore_utility(ops)

def test_003_init_secondary():
    global node2
    node2 = cluster.create_datanode("/tmp/listen/node2", listen_flag=True)
    node2.set_gp_params(gp_dbid = 8, port = 7001)
    node2.create()
    node2.run()
    config_standby(node1, node2)
    assert node2.wait_until_state(target_state="secondary")
    assert node1.wait_until_state(target_state="primary")

@unittest.skip('read from standby')
def test_004_read_from_secondary():
    results = node2.run_sql_query("SELECT * FROM t1 ORDER BY a")
    assert results == [(1,), (2,)]

@raises(Exception)
def test_005_writes_to_node2_fail():
    node2.run_sql_query("INSERT INTO t1 VALUES (3)")

def test_006_fail_primary():
    node1.fail()
    assert node2.wait_until_state(target_state="wait_primary")

def test_007_writes_to_node2_succeed():
    ops = set_utility(False)
    node2.run_sql_query("INSERT INTO t1 VALUES (3)")
    results = node2.run_sql_query("SELECT * FROM t1 ORDER BY a")
    assert results == [(1,), (2,), (3,)]
    restore_utility(ops)

def test_008_start_node1_again():
    node1.run()
    assert node2.wait_until_state(target_state="primary")
    assert node1.wait_until_state(target_state="secondary")

@unittest.skip('read from standby')
def test_009_read_from_new_secondary():
    results = node1.run_sql_query("SELECT * FROM t1")
    assert results == [(1,), (2,), (3, )]

@raises(Exception)
def test_010_writes_to_node1_fail():
    node1.run_sql_query("INSERT INTO t1 VALUES (3)")

def test_011_fail_secondary():
    node1.fail()
    assert node2.wait_until_state(target_state="wait_primary")
