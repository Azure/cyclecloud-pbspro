#!/bin/bash
# Example
# server_dyn_res: "myres !/path/to/my/script.sh"
# becomes
# server_dyn_res: "myres !/opt/cycle/pbspro/serv_dyn_res_wrapper.sh myres /path/to/my/script.sh"
res_name=$1
shift
$@ > /opt/cycle/pbspro/server_dyn_res/$res_name
cat /opt/cycle/pbspro/server_dyn_res/$res_name