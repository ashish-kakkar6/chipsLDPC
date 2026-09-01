package chipsldpc

import chisel3._

final class TwoMinHarness(degree: Int, bits: Int) extends Module {
  val io = IO(new Bundle {
    val inputs = Input(Vec(degree, UInt(bits.W)))
    val result = Output(new MinPair(bits))
  })
  private val core = Module(new TwoMin(degree, bits))
  core.inputs := io.inputs
  io.result := core.result
}

final class CheckNodeHarness(config: CheckConfig) extends Module {
  val io = IO(new Bundle {
    val inputs     = Input(Vec(config.degree, new SignMag(config.q.magnitudeBits)))
    val syndrome   = Input(Bool())
    val scaleShift = Input(UInt(config.scale.controlBits.W))
    val result     = Output(new CheckResult(config))
  })
  private val core = Module(new CheckNode(config))
  core.inputs := io.inputs
  core.syndrome := io.syndrome
  core.scaleShift.foreach(_ := io.scaleShift)
  io.result := core.result
}

final class VariableNodeHarness(config: VariableConfig) extends Module {
  val io = IO(new Bundle {
    val inputs = Input(Vec(config.degree, new CheckMessage(config.q.magnitudeBits)))
    val prior  = Input(SInt(config.q.accumulatorBits.W))
    val result = Output(new VariableResult(config))
  })
  private val core = Module(new VariableNode(config))
  core.inputs := io.inputs
  core.prior := io.prior
  io.result := core.result
}

final class RelayVariableNodeHarness(config: VariableConfig, format: RelayFormat) extends Module {
  val io = IO(new Bundle {
    val inputs   = Input(Vec(config.degree, new CheckMessage(config.q.magnitudeBits)))
    val prior    = Input(SInt(config.q.accumulatorBits.W))
    val previous = Input(SInt(config.q.accumulatorBits.W))
    val beta     = Input(UInt(format.betaBits.W))
    val bias     = Output(SInt(config.q.accumulatorBits.W))
    val result   = Output(new VariableResult(config))
  })
  private val core = Module(new RelayVariableNode(config, format))
  core.inputs := io.inputs
  core.prior := io.prior
  core.previousMarginal := io.previous
  core.beta := io.beta
  io.bias := core.bias
  io.result := core.result
}
