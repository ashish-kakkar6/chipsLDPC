# Preliminary core-only timing model.
# The wide packed data ports are internal block boundaries, not package pins.

if {![info exists ::BB144_CLOCK_PERIOD_NS]} {
  error "BB144_CLOCK_PERIOD_NS must be set by run_ooc.tcl"
}

create_clock -name core_clk -period $::BB144_CLOCK_PERIOD_NS [get_ports clock]
# Conservative characterization assumption for both setup and hold. The board
# build must replace this with uncertainty derived from its oscillator/MMCM.
set_clock_uncertainty 0.200 [get_clocks core_clk]

# Measure only genuine register-to-register paths in this OOC pass. Interface
# timing is measured later in the complete board/BIST implementation.
set non_clock_inputs [remove_from_collection [all_inputs] [get_ports clock]]
set_false_path -from $non_clock_inputs
set_false_path -to [all_outputs]
