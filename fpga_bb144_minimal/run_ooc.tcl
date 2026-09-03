# Minimal non-project Vivado flow for a graph-specialized chipsLDPC core.
#
# Usage:
#   vivado -mode batch -source run_ooc.tcl -tclargs \
#     RTL PART PERIOD_NS OUT_DIR ?TOP?

if {$argc < 4 || $argc > 5} {
  error "usage: run_ooc.tcl RTL PART PERIOD_NS OUT_DIR ?TOP?"
}

set rtl        [file normalize [lindex $argv 0]]
set part       [lindex $argv 1]
set period_ns  [lindex $argv 2]
set out_dir    [file normalize [lindex $argv 3]]
set top        StaticTannerArtifact
if {$argc == 5} {
  set top [lindex $argv 4]
}
set script_dir [file dirname [file normalize [info script]]]
set xdc        [file join $script_dir core_ooc.xdc]
set report_dir [file join $out_dir reports]
set dcp_dir    [file join $out_dir checkpoints]
set metadata_path [file join $out_dir run_metadata.txt]
set start_epoch [clock seconds]

if {![file isfile $rtl]} {
  error "RTL file does not exist: $rtl"
}
if {![string is double -strict $period_ns] || $period_ns <= 0.0} {
  error "PERIOD_NS must be a positive number"
}
if {![file isfile $xdc]} {
  error "OOC constraint file does not exist: $xdc"
}
if {[llength [get_parts -quiet $part]] != 1} {
  error "Vivado part is unavailable or ambiguous: $part"
}
foreach stale [list $report_dir $dcp_dir $metadata_path] {
  if {[file exists $stale]} {
    error "OUT_DIR contains stale results; choose a fresh directory: $stale"
  }
}

file mkdir $report_dir
file mkdir $dcp_dir

set metadata [open $metadata_path w]
puts $metadata "initial_status=STARTED"
puts $metadata "start_utc=[clock format $start_epoch -gmt true -format {%Y-%m-%dT%H:%M:%SZ}]"
puts $metadata "vivado=[version -short]"
puts $metadata "part=$part"
puts $metadata "top=$top"
puts $metadata "clock_period_ns=$period_ns"
puts $metadata "clock_uncertainty_ns=0.200_setup_and_hold"
puts $metadata "rtl=$rtl"
puts $metadata "timing_scope=OOC register-to-register only; interface paths false-pathed"
close $metadata

set ::BB144_CLOCK_PERIOD_NS $period_ns
read_verilog -sv $rtl
read_xdc $xdc

synth_design -top $top -part $part -mode out_of_context -flatten_hierarchy rebuilt
write_checkpoint -force [file join $dcp_dir post_synth.dcp]
report_utilization -hierarchical -hierarchical_depth 3 \
  -file [file join $report_dir post_synth_util.rpt]
report_timing_summary -delay_type min_max -max_paths 20 -report_unconstrained \
  -file [file join $report_dir post_synth_timing.rpt]
check_timing -verbose -file [file join $report_dir post_synth_check_timing.rpt]

if {[llength [get_ports -quiet clock]] != 1} {
  error "expected exactly one top-level port named clock"
}
if {[llength [get_clocks -quiet core_clk]] != 1} {
  error "expected exactly one timing clock named core_clk"
}
set black_boxes [get_cells -quiet -hierarchical -filter {IS_BLACKBOX == TRUE}]
if {[llength $black_boxes] != 0} {
  error "synthesis left [llength $black_boxes] black-box cells"
}

opt_design
place_design
phys_opt_design
route_design

write_checkpoint -force [file join $dcp_dir post_route.dcp]
report_route_status -file [file join $report_dir route_status.rpt]
report_utilization -hierarchical -hierarchical_depth 3 \
  -file [file join $report_dir post_route_util.rpt]
report_timing_summary -delay_type min_max -max_paths 20 -report_unconstrained \
  -file [file join $report_dir post_route_timing.rpt]
report_timing -delay_type max \
  -max_paths 20 -sort_by group -file [file join $report_dir reg_to_reg_timing.rpt]
check_timing -verbose -file [file join $report_dir post_route_check_timing.rpt]
report_clock_utilization -file [file join $report_dir clock_util.rpt]
report_design_analysis -congestion -file [file join $report_dir congestion.rpt]
report_drc -file [file join $report_dir drc.rpt]
report_methodology -file [file join $report_dir methodology.rpt]
if {[llength [info commands report_high_fanout_nets]] != 0} {
  if {[catch {
    report_high_fanout_nets -max_nets 50 \
      -file [file join $report_dir high_fanout_nets.rpt]
  } message]} {
    puts "INFO: high-fanout report unavailable: $message"
  }
}

if {[llength [info commands get_slrs]] != 0 && [llength [get_slrs -quiet *]] > 1} {
  if {[catch {
    report_utilization -slr -file [file join $report_dir slr_util.rpt]
  } message]} {
    puts "INFO: per-SLR utilization report unavailable: $message"
  }
  if {[catch {
    report_slr_crossing -file [file join $report_dir slr_crossing.rpt]
  } message]} {
    puts "INFO: SLR crossing report unavailable: $message"
  }
}

set setup_paths [get_timing_paths -quiet -delay_type max -max_paths 1]
set hold_paths  [get_timing_paths -quiet -delay_type min -max_paths 1]
if {[llength $setup_paths] == 0 || [llength $hold_paths] == 0} {
  error "no valid setup and/or hold timing path; inspect check_timing reports"
}
set wns [get_property SLACK [lindex $setup_paths 0]]
set whs [get_property SLACK [lindex $hold_paths 0]]
set routed_fully [report_route_status -boolean_check ROUTED_FULLY]
set routing_errors [report_route_status -boolean_check ERRORS_IN_ROUTES]
set blocking_drc_checks \
  [get_drc_checks -quiet -filter {SEVERITY == Error || SEVERITY == Fatal}]
set error_drcs {}
foreach check $blocking_drc_checks {
  set check_name [get_property NAME $check]
  foreach violation [get_drc_violations -quiet $check_name] {
    lappend error_drcs $violation
  }
}
set timing_met [expr {$wns >= 0.0 && $whs >= 0.0}]

set metadata [open $metadata_path a]
puts $metadata "end_utc=[clock format [clock seconds] -gmt true -format {%Y-%m-%dT%H:%M:%SZ}]"
puts $metadata "elapsed_seconds=[expr {[clock seconds] - $start_epoch}]"
puts $metadata "wns_ns=$wns"
puts $metadata "whs_ns=$whs"
puts $metadata "routed_fully=$routed_fully"
puts $metadata "routing_errors=$routing_errors"
puts $metadata "error_drc_count=[llength $error_drcs]"
if {!$routed_fully || $routing_errors} {
  puts $metadata "status=UNROUTED"
} elseif {[llength $error_drcs] != 0} {
  puts $metadata "status=DRC_FAILED"
} elseif {!$timing_met} {
  puts $metadata "status=TIMING_NOT_MET"
} else {
  puts $metadata "status=PASS"
}
close $metadata

if {!$routed_fully || $routing_errors} {
  error "UNROUTED: routed_fully=$routed_fully, routing_errors=$routing_errors; reports are in $report_dir"
}
if {[llength $error_drcs] != 0} {
  error "DRC_FAILED: [llength $error_drcs] error-severity violations; reports are in $report_dir"
}
if {!$timing_met} {
  error "TIMING_NOT_MET: WNS=$wns ns, WHS=$whs ns; reports are in $report_dir"
}
puts "PASS: routed OOC timing met; WNS=$wns ns, WHS=$whs ns; reports are in $report_dir"
