#!/bin/bash

. /usr/local/greenplum-db-devel/greenplum_path.sh

set -e
if [[ -z "$DATADIRS" ]]; then
    DATADIRS=$HOME/datadirs
fi
# Adjust this to set the number of segment servers to set up. Two is the
# minimum that makes sense.
NUM_SEGMENTS=3
mkdir -p $DATADIRS
pushd $DATADIRS

function init_segments() {
initdb -k -n -D data-master
}
# pgauto-{0...5}
# index is: 0, 1, 2
# pgauto-0 172.27.1.2 7002 primary0
# pgauto-1 172.27.1.3 7005 mirror0
# pgauto-2 172.27.1.4 7003 primary1
# pgauto-3 172.27.1.5 7006 mirror1
# pgauto-4 172.27.1.6 7004 primary2
# pgauto-5 172.27.1.7 7007 mirror2
function init_segment() {
    local index="$1"
    cp -ar data-master data-primary$index
cat >> data-primary$index/postgresql.conf <<EOF
listen_addresses='*'
fsync=on
optimizer=off
gp_contentid=$index
EOF
cat >> data-primary$index/pg_hba.conf <<EOF
host    all             all             172.27.1.0/24                 trust
hostssl    all             all             172.27.1.0/24                 trust
host    replication     all             172.27.1.0/24            trust
hostssl    replication     all             172.27.1.0/24            trust
EOF
    local myport=$((7002 + index))
    echo "gp_dbid=$((2+index))" > data-primary$index/internal.auto.conf
    local nsIdx=$((index*2)) # 0,2,4
    sudo ip netns exec pgauto-$nsIdx su gpadmin -c ". /usr/local/greenplum-db-devel/greenplum_path.sh ; pg_ctl -D $DATADIRS/data-primary$index -o \"-p $myport -c gp_role=execute\" start"
    sudo ip netns exec pgauto-$((nsIdx+1)) su gpadmin -c ". /usr/local/greenplum-db-devel/greenplum_path.sh ; pg_basebackup -D data-mirror$index -R -X stream -C --slot=internal_wal_replication_slot -d \"host=172.27.1.$((nsIdx+2)) port=$myport dbname=postgres\" --target-gp-dbid $((5+index))"
    sudo ip netns exec pgauto-$((nsIdx+1)) su gpadmin -c ". /usr/local/greenplum-db-devel/greenplum_path.sh ; pg_ctl -D $DATADIRS/data-mirror$index -o \"-p $((myport+3)) -c gp_role=execute\" start"
}

function init_segment2() {
    local segindex="$2"
    local dbid="$3"
    local ippref="$4"
    local ipnum="$5"
    local myport="$6"
    local stride="$7"

    cp -ar data-master data-primary$segindex
cat >> data-primary$segindex/postgresql.conf <<EOF
listen_addresses='*'
fsync=on
optimizer=off
gp_contentid=$segindex
EOF
cat >> data-primary$segindex/pg_hba.conf <<EOF
host    all             all             ${ippref}.0/24                 trust
hostssl    all             all             ${ippref}.0/24                 trust
host    replication     all             ${ippref}.0/24            trust
hostssl    replication     all             ${ippref}.0/24            trust
EOF
    echo "gp_dbid=$dbid" > data-primary$segindex/internal.auto.conf
    local nsIdx=$((segindex*2)) # 0,2,4
    sudo ip netns exec pgauto-$nsIdx su gpadmin -c ". /usr/local/greenplum-db-devel/greenplum_path.sh ; pg_ctl -D $DATADIRS/data-primary$segindex -o \"-p $myport -c gp_role=execute\" start"
    sudo ip netns exec pgauto-$((nsIdx+1)) su gpadmin -c ". /usr/local/greenplum-db-devel/greenplum_path.sh ; pg_basebackup -D data-mirror$segindex -R -X stream -C --slot=internal_wal_replication_slot -d \"host=${ippref}.$ipnum port=$myport dbname=postgres\" --target-gp-dbid $((dbid+stride))"
    sudo ip netns exec pgauto-$((nsIdx+1)) su gpadmin -c ". /usr/local/greenplum-db-devel/greenplum_path.sh ; pg_ctl -D $DATADIRS/data-mirror$segindex -o \"-p $((myport+stride)) -c gp_role=execute\" start"
}
# datadir
function config_master() {
local datadir="$1"
cp -r $DATADIRS/data-master $datadir
cat >> $datadir/postgresql.conf <<EOF
fsync=on
optimizer=off
gp_contentid=-1
EOF
echo "gp_dbid=1" > $datadir/internal.auto.conf
}

# pg_hba.conf
# datadir
function config_monitor() {
    datadir="$1"
    echo 'host "pg_auto_failover" "autoctl_node" 172.27.1.0/24  md5' >> $datadir/pg_hba.conf
    echo 'hostssl "pg_auto_failover" "autoctl_node" 172.27.1.0/24  md5' >> $datadir/pg_hba.conf
    echo 'host "pg_auto_failover" "autoctl_node" 172.27.1.0/24  trust' >> $datadir/pg_hba.conf
    echo 'hostssl "pg_auto_failover" "autoctl_node" 172.27.1.0/24  trust' >> $datadir/pg_hba.conf
}

function start_segments() {
for ((i=0; i<$NUM_SEGMENTS; i++))
do
    portP=$((7002+i))
    portM=$((7005+i))
    pg_ctl -D $DATADIRS/data-primary$i -o "-p $portP -c gp_role=execute" start
    pg_ctl -D $DATADIRS/data-mirror$i -o "-p $portM -c gp_role=execute" start
done
}

function stop_segments() {
for ((i=0; i<$NUM_SEGMENTS; i++))
do
    pg_ctl -D $DATADIRS/data-primary$i -m immediate stop 2>/dev/null || true
    pg_ctl -D $DATADIRS/data-mirror$i -m immediate stop 2>/dev/null || true

    portP=$((7002+i))
    portM=$((7005+i))
    rm -rf /tmp/.s.PGSQL.${portP}.* 2>/dev/null || true
    rm -rf /tmp/.s.PGSQL.${portM}.* 2>/dev/null || true
done
}

function restart_segments() {
stop_segments
start_segments
}

function reload_segments() {
for ((i=0; i<$NUM_SEGMENTS; i++))
do
    pg_ctl -D $DATADIRS/data-primary$i -s reload 2>/dev/null || true
    pg_ctl -D $DATADIRS/data-mirror$i -s reload 2>/dev/null || true
done
}
case $1 in
init)
    init_segments
    ;;
init_segment)
    init_segment "$2"
    ;;
init_segment2)
    init_segment "$2" "$3" "$4" "$5" "$6" "$7" "$8"
    ;;
start)
    start_segments
    ;;
stop)
    stop_segments
    ;;
restart)
    restart_segments
    ;;
destroy)
    stop_segments
    rm -rf data-primary* data-mirror* data-master 2>/dev/null || true
    ;;
config_monitor)
    config_monitor "$2"
    ;;
config_master)
    # datadir
    config_master "$2"
    ;;
init_gp_segment_configuration)
    postgres --single -D "$2" -O postgres <<EOF
$3
EOF
    ;;
config_gp_segments)
    # datadir, host, port, 
    config_gp_segments "$2" "$3" "$4"
    ;;
*)
    echo "unknown commands $1"
    ;;
esac

popd
