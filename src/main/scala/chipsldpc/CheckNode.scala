package chipsldpc

import chisel3._

final class CheckNode(config: CheckConfig) extends RawModule {
  val inputs     = IO(Input(Vec(config.degree, new SignMag(config.q.magnitudeBits))))
  val syndrome   = IO(Input(Bool()))
  val scaleShift = config.scale match {
    case _: RampScale => Some(IO(Input(UInt(config.scale.controlBits.W))))
    case _            => None
  }
  val result     = IO(Output(new CheckResult(config)))

  private val signs = inputs.map(Arithmetic.hardDecision)
  private val parity = VecInit(signs).asUInt.xorR ^ syndrome
  private val (first, second) = TwoMinLogic(inputs.map(_.magnitude))
  private val control = scaleShift.getOrElse(0.U)
  private val scaledFirst = Arithmetic.scale(first, control, config.scale, config.q.magnitudeBits)
  private val scaledSecond = Arithmetic.scale(second, control, config.scale, config.q.magnitudeBits)

  result.minima.first := scaledFirst
  result.minima.second := scaledSecond
  result.edges.zipWithIndex.foreach { case (edge, i) =>
    edge.useSecond := inputs(i).magnitude === first
    edge.sign := parity ^ signs(i)
  }
}

final class CheckNodeUnit(config: CheckConfig) extends Module {
  val io = IO(new Bundle {
    val valid      = Input(Bool())
    val inputs     = Input(Vec(config.degree, new SignMag(config.q.magnitudeBits)))
    val syndrome   = Input(Bool())
    val scaleShift = Input(UInt(config.scale.controlBits.W))
    val outValid   = Output(Bool())
    val result     = Output(new CheckResult(config))
  })

  private val core = Module(new CheckNode(config))
  core.inputs := io.inputs
  core.syndrome := io.syndrome
  core.scaleShift.foreach(_ := io.scaleShift)

  private val result = RegInit(0.U.asTypeOf(new CheckResult(config)))
  when(io.valid) { result := core.result }
  io.result := result
  io.outValid := RegNext(io.valid, false.B)
}
