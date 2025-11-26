import pytest
from unittest.mock import Mock

from pbspro.scheduler import read_schedulers, PBSProScheduler


def test_read_schedulers_with_fqdn_hostnames():
    """Test that read_schedulers handles FQDN hostnames correctly when there's a mismatch
    between scheduler host (FQDN) and server host (short name)."""
    
    # Mock pbscmd
    pbscmd = Mock()
    
    # Mock scheduler dict with FQDN hostname
    sched_dicts = [
        {
            "name": "default",
            "sched_host": "headnode.internal.cloudapp.net",  # FQDN
            "sched_log": "/var/spool/pbs/sched_logs",
            "sched_priv": "/var/spool/pbs/sched_priv",
            "state": "Idle",
            "scheduling": "True",
            "pbs_version": "20.0.1"
        }
    ]
    
    # Mock server dict with short hostname
    server_dicts = [
        {
            "name": "default",
            "server_host": "headnode",  # Short hostname
            "state": "Active",
            "scheduling": "True",
            "pbs_version": "20.0.1"
        }
    ]
    
    pbscmd.qmgr_parsed.side_effect = lambda cmd, obj_type: {
        ("list", "sched"): sched_dicts,
        ("list", "server"): server_dicts
    }[(cmd, obj_type)]
    
    # Mock resource definitions
    resource_definitions = {}
    
    # This should now work with the fix
    result = read_schedulers(pbscmd, resource_definitions)
    
    # Should return one scheduler
    assert len(result) == 1
    assert "headnode" in result
    assert isinstance(result["headnode"], PBSProScheduler)


def test_read_schedulers_with_matching_hostnames():
    """Test that read_schedulers works correctly when hostnames match."""
    
    # Mock pbscmd
    pbscmd = Mock()
    
    # Mock scheduler dict with short hostname
    sched_dicts = [
        {
            "name": "default",
            "sched_host": "headnode",  # Short hostname
            "sched_log": "/var/spool/pbs/sched_logs",
            "sched_priv": "/var/spool/pbs/sched_priv",
            "state": "Idle",
            "scheduling": "True",
            "pbs_version": "20.0.1"
        }
    ]
    
    # Mock server dict with short hostname
    server_dicts = [
        {
            "name": "default",
            "server_host": "headnode",  # Short hostname
            "state": "Active",
            "scheduling": "True",
            "pbs_version": "20.0.1"
        }
    ]
    
    pbscmd.qmgr_parsed.side_effect = lambda cmd, obj_type: {
        ("list", "sched"): sched_dicts,
        ("list", "server"): server_dicts
    }[(cmd, obj_type)]
    
    # Mock resource definitions
    resource_definitions = {}
    
    # This should work fine
    result = read_schedulers(pbscmd, resource_definitions)
    
    # Should return one scheduler
    assert len(result) == 1
    assert "headnode" in result
    assert isinstance(result["headnode"], PBSProScheduler)


def test_read_schedulers_with_mixed_hostname_formats():
    """Test that read_schedulers handles mixed FQDN and short hostname formats."""
    
    # Mock pbscmd
    pbscmd = Mock()
    
    # Mock scheduler dicts with mixed hostname formats
    sched_dicts = [
        {
            "name": "default",
            "sched_host": "headnode.internal.cloudapp.net",  # FQDN
            "sched_log": "/var/spool/pbs/sched_logs", 
            "sched_priv": "/var/spool/pbs/sched_priv",
            "state": "Idle",
            "scheduling": "True",
            "pbs_version": "20.0.1"
        },
        {
            "name": "scheduler2",
            "sched_host": "compute001",  # Short hostname
            "sched_log": "/var/spool/pbs/sched_logs2",
            "sched_priv": "/var/spool/pbs/sched_priv2", 
            "state": "Idle",
            "scheduling": "True",
            "pbs_version": "20.0.1"
        }
    ]
    
    # Mock server dicts with mixed hostname formats
    server_dicts = [
        {
            "name": "default",
            "server_host": "headnode",  # Short hostname
            "state": "Active",
            "scheduling": "True",
            "pbs_version": "20.0.1"
        },
        {
            "name": "scheduler2", 
            "server_host": "compute001.domain.com",  # FQDN
            "state": "Active",
            "scheduling": "True",
            "pbs_version": "20.0.1"
        }
    ]
    
    pbscmd.qmgr_parsed.side_effect = lambda cmd, obj_type: {
        ("list", "sched"): sched_dicts,
        ("list", "server"): server_dicts
    }[(cmd, obj_type)]
    
    # Mock resource definitions
    resource_definitions = {}
    
    # This should work with the fix 
    result = read_schedulers(pbscmd, resource_definitions)
    
    # Should return two schedulers
    assert len(result) == 2
    assert "headnode" in result
    assert "compute001" in result
    assert isinstance(result["headnode"], PBSProScheduler)
    assert isinstance(result["compute001"], PBSProScheduler)