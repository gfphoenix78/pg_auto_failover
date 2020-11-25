import os
import subprocess
import pgautofailover_utils as pgautofailover

def datadirs_for_segments():
    datadirs = os.environ.get('DATADIRS', '')
    if datadirs == '':
        os.environ['DATADIRS'] = os.path.join('/home/gpadmin', 'datadirs')
    return datadirs

node_list = []

def node2ip(node):
    return str(node.vnode.address)

def split_ip(ipv4):
    ip = ipv4.strip().split('/')
    print("IP:", ip)
    x = ip[0].split('.')
    print("Split IP:", x)
    assert len(x) == 4
    return '.'.join(x[:3]), str(x[3])

def init_greenplum_env(cluster):
    global node_list
    reset_utility()
    node_list = [cluster.vlan.create_node() for i in range(6)]
    (prefix, index) = split_ip(str(node_list[0].address))
    init_gp_segments()
    dbid = 2
    port = 7002
    for i in range(3):
        init_gp_segment2(i, dbid, prefix, index, port, 3)
        dbid += 1
        port += 1

def standby_gp_segment_configuration(datadir, addr, port, dbid):
    hostname = '172.27.1.1'
    return "insert into gp_segment_configuration values(%d, -1, 'm','m','s','u',%d, '%s','%s','%s')" % (
            dbid, port, hostname, addr, datadir)

def insert_gp_segment_configuartion(node_addrs, mdatadir, maddr, mport):
    datadirs = datadirs_for_segments()
    hostname = os.environ['HOSTNAME']
    hostname = '172.27.1.1'
    datadirs = '/home/gpadmin/datadirs'
    sql = 'delete from gp_segment_configuration;\ninsert into gp_segment_configuration values'
    sql += "  (1, -1, 'p', 'p', 's', 'u', %d, '%s', '%s', '%s')" % (mport, hostname, maddr, mdatadir)
    for i in range(3):
        sql += ", (%d, %d, 'p', 'p', 's', 'u', %d, '%s', '%s', '%s/data-primary%d')" % (2+i, i, 7002+i, hostname, node_addrs[2*i], datadirs, i)
        sql += ", (%d, %d, 'm', 'm', 's', 'u', %d, '%s', '%s', '%s/data-mirror%d')"  % (5+i, i, 7005+i, hostname, node_addrs[2*i+1], datadirs, i)

    print('datadirs =', datadirs)
    print('hostname =', hostname)
    print('gp_segment_configuration:', sql)
    return sql

# prepare pgdata for all segments
def init_gp_segments():
    user = os.environ['USER']
    rc = subprocess.run(['su', user, '-c', 'bash segments_util.sh destroy'])
    assert rc.returncode == 0
    rc = subprocess.run(['su', user, '-c', 'bash segments_util.sh init'])
    assert rc.returncode == 0

def init_gp_segment2(seg_index, dbid, ip_prefix, ip_number, port, stride):
    user = os.environ['USER']
    cmd = ['bash segments_util.sh init_segment2', str(seg_index), str(dbid), ip_prefix, ip_number, str(port), str(stride)]
    rc = subprocess.run(['su', user, '-c', ' '.join(cmd)])
    assert rc.returncode == 0

def init_gp_segment(index):
    user = os.environ['USER']
    cmd = ['bash segments_util.sh init_segment', str(index)]
    rc = subprocess.run(['su', user, '-c', ' '.join(cmd)])
    assert rc.returncode == 0


def destroy_gp_segments():
    user = os.environ['USER']
    rc = subprocess.run(['su', user, '-c', 'bash segments_util.sh destroy'])
    assert rc.returncode == 0

def config_node(datadir, dbid):
    user = os.environ['USER']
    cmd = ['bash segments_util.sh config_node', datadir, str(dbid)]
    rc = subprocess.run(['su', user, '-c', ' '.join(cmd)])
    assert rc.returncode == 0

def config_master(cluster, datadir, port):
    vnode = cluster.monitor.vnode
    pref, ipnum = split_ip(str(vnode.address))

    user = os.environ['USER']
    cmd = ['bash segments_util.sh config_master', datadir]
    rc = subprocess.run(['su', user, '-c', ' '.join(cmd)])
    assert rc.returncode == 0
    
    node_addrs = [str(x.address) for x in node_list]
    sql = insert_gp_segment_configuartion(node_addrs, datadir, "%s.%d" % (pref, int(ipnum)+1), port)
    cmd = ['bash segments_util.sh init_gp_segment_configuration', datadir, '"', sql, '"']
    rc = subprocess.run(['su', user, '-c', ' '.join(cmd)])
    assert rc.returncode == 0

def config_standby(primary_node, datadir, addr, port, dbid):
    ops = set_utility(True)
    os.environ['PGOPTIONS'] = '-c gp_role=utility -c allow_system_table_mods=on'
    sql = standby_gp_segment_configuration(datadir, addr, port, dbid)
    primary_node.run_sql_query(sql)
    restore_utility(ops)

# create pg node by running pg_basebackup 
def init_standby(datadir, index, port):
    user = os.environ['USER']
    cmd = ['bash segments_util.sh init_standby', datadir, str(index), str(port)]
    rc = subprocess.run(['su', user, '-c', ' '.join(cmd)])
    assert rc.returncode == 0


def config_monitor(node):
    print('config monitor:', os.getcwd())
    user = os.environ['USER']
    cmd = ['bash segments_util.sh config_monitor', node.datadir]
    print(' '.join(cmd))
    rc = subprocess.run(['su', user, '-c', ' '.join(cmd)])
    assert rc.returncode == 0

def reset_utility():
    set_utility(True)
def set_utility(utility=True):
    ops = os.environ.get('PGOPTIONS', '')
    os.environ['PGOPTIONS'] = '-c gp_role=utility' if utility else ''
    return ops
def restore_utility(ops):
    os.environ['PGOPTIONS'] = ops


if __name__ == '__main__':
    init_gp_segments()

