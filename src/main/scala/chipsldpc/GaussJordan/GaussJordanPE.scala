package chipsldpc.GaussJordan

import chisel3._

object GjOpcode extends ChiselEnum {
  val Pass = Value(0.U)
  val Swap = Value(1.U)
  val Add  = Value(2.U)
  val Lock = Value(3.U)
}

final class PeCol extends RawModule {
  override def desiredName: String = "pe_col"

  val clk     = IO(Input(Clock()))
  val rst     = IO(Input(Bool()))
  val en_i    = IO(Input(Bool()))
  val data_i  = IO(Input(Bool()))
  val op_i    = IO(Input(GjOpcode()))
  val op_o    = IO(Output(GjOpcode()))
  val data_o  = IO(Output(Bool()))
  val state_o = IO(Output(Bool()))

  private val (r, dataReg, opReg) = withClockAndReset(clk, rst) {
    (RegInit(false.B), RegInit(false.B), RegInit(GjOpcode.Pass))
  }
  private val rNext = WireDefault(r)
  private val dataNext = WireDefault(data_i)

  when(op_i === GjOpcode.Add) {
    dataNext := r ^ data_i
  }.elsewhen(op_i.isOneOf(GjOpcode.Swap, GjOpcode.Lock)) {
    rNext := data_i
    dataNext := r
  }

  when(en_i) {
    r := rNext
    dataReg := dataNext
    opReg := op_i
  }

  op_o := opReg
  data_o := dataReg
  state_o := r
}

final class PeDiag extends RawModule {
  override def desiredName: String = "pe_diag"

  val clk          = IO(Input(Clock()))
  val rst          = IO(Input(Bool()))
  val en_i         = IO(Input(Bool()))
  val data_i       = IO(Input(Bool()))
  val reduce_sig_i = IO(Input(Bool()))
  val data_o       = IO(Output(Bool()))
  val state_o      = IO(Output(Bool()))
  val op_o         = IO(Output(GjOpcode()))
  val reduce_sig_o = IO(Output(Bool()))

  private val (r, dataReg, opReg) = withClockAndReset(clk, rst) {
    (RegInit(false.B), RegInit(false.B), RegInit(GjOpcode.Pass))
  }
  private val rNext = WireDefault(r)
  private val dataNext = WireDefault(false.B)
  private val opNext = WireDefault(GjOpcode.Pass)

  when(reduce_sig_i && r) {
    dataNext := data_i
    opNext := GjOpcode.Swap
  }.elsewhen(!data_i) {
    // Defaults implement pass.
  }.elsewhen(!r) {
    rNext := true.B
    opNext := GjOpcode.Lock
  }.otherwise {
    opNext := GjOpcode.Add
  }

  when(en_i) {
    r := rNext
    dataReg := dataNext
    opReg := opNext
  }

  data_o := dataReg
  state_o := r
  op_o := opReg
  reduce_sig_o := reduce_sig_i && !rst
}
