name "pbspro_master_role"
description "Open PBSPro Master Role"
run_list("role[scheduler]",
  "recipe[cshared::directories]",
  "recipe[pbspro::skel]",
  "recipe[cuser]",
  "recipe[cshared::server]",
  "recipe[pbspro::scheduler]",
  "recipe[cganglia::server]")

default_attributes "cyclecloud" => { "discoverable" => true }
