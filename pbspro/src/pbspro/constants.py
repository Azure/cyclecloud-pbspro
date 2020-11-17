class PBSProJobStates:
    Begun = "B"
    Exiting = "E"
    Finished = "F"
    Held = "H"
    Moved = "M"
    Queued = "Q"
    Running = "R"
    Suspended = "S"
    Transition = "T"
    Waiting = "W"
    SubJobExiting = "X"


{
    "B": 7,  # job array has begun (at least one job has started)
    "E": 5,  # Exiting
    "F": 9,  # Finished
    "H": 2,  # Held
    "M": 8,  # Moved
    "Q": 1,  # Queued
    "R": 4,  # Running
    "S": None,  # suspended by scheduler. Only appears as a substate
    "T": 0,  # transition to/from a server
    "U": None,  # suspended because execute node is busy (i.e. using workstations)
    "W": 3,  # Waiting for execution time OR delayed due to a staging failure
    "X": 6,  # Subjob is finished
}


class ServerStates:
    Hot_Start = "Hot_Start"
    Idle = "Idle"
    Scheduling = "Scheduling"
    Terminating = "Terminating"
    Terminating_Delayed = "Terminating_Delayed"


class VNodeStates:
    busy = "busy"
    down = "down"
    free = "free"
    job_busy = "job-busy"
    job_exclusive = "job-exclusive"
    maintenance = "maintenance"
    offline = "offline"
    powered_off = "powered-off"
    powering_down = "powering-down"
    powering_on = "powering-on"
    provisioning = "provisioning"
    resv_exclusive = "resv-exclusive"
    sleep = "sleep"
    stale = "stale"
    state_unknown = "state-unknown"
    state_unknown_down = "state-unknown,down"
    unresolvable = "unresolvable"
    wait_provisioning = "wait-provisioning"
