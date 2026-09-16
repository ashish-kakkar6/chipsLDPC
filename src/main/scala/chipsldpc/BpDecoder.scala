package chipsldpc

import chisel3._
import chisel3.util.{Decoupled, Enum, log2Ceil}
import chipsldpc.graph.TannerNodeGraphs

final case class VanillaBpConfig(
    nodes: TannerNodeGraphs,
    iterations: Int,
    q: Quantization = RelayDefaults.q,
    scale: CheckScale = RelayDefaults.scale,
) {
  require(iterations > 0)
  val graph = nodes.graph
  val iterationBits: Int = math.max(1, log2Ceil(iterations + 1))
}

/**
  * Common handoff record for BP-family decoders and optional post-processors.
  * `correction`/`residual` describe the selected proposal; Relay keeps
  * `marginal` as the final leg's soft state for a downstream processor.
  */
final class BpDecoderResult(
    checks: Int,
    variables: Int,
    q: Quantization,
    iterationBits: Int,
    legBits: Int,
    solutionBits: Int,
) extends Bundle {
  val success = Bool()
  val correction = Vec(variables, Bool())
  val marginal = Vec(variables, SInt(q.accumulatorBits.W))
  val residual = Vec(checks, Bool())
  val totalIterations = UInt(iterationBits.W)
  val legsExecuted = UInt(legBits.W)
  val solutionsFound = UInt(solutionBits.W)
}

/** Autonomous early-terminating min-sum BP. */
final class VanillaBpDecoder(config: VanillaBpConfig) extends Module {
  val io = IO(new Bundle {
    val in = Flipped(Decoupled(new StaticDecoderInput(
      config.graph.checkCount, config.graph.variableCount, config.q,
    )))
    val out = Decoupled(new BpDecoderResult(
      config.graph.checkCount, config.graph.variableCount, config.q,
      config.iterationBits, legBits = 1, solutionBits = 1,
    ))
  })

  private val sIdle :: sRun :: sOutput :: Nil = Enum(3)
  private val state = RegInit(sIdle)
  private val iteration = RegInit(0.U(config.iterationBits.W))
  private val outcome = Reg(chiselTypeOf(io.out.bits))
  private val core = Module(new StaticTannerCore(config.nodes, config.q, config.scale))
  private val completed = iteration + 1.U
  private val controlMax = (BigInt(1) << config.scale.controlBits) - 1

  core.io.load.valid := state === sIdle && io.in.valid
  core.io.load.bits := io.in.bits
  core.io.step.valid := state === sRun
  core.io.step.bits := Mux(completed > controlMax.U, controlMax.U, completed)(
    config.scale.controlBits - 1, 0,
  )
  core.io.bias := core.io.prior
  core.io.restartMessages := false.B

  io.in.ready := state === sIdle && core.io.load.ready
  io.out.valid := state === sOutput
  io.out.bits := outcome

  when(io.in.fire) {
    iteration := 0.U
    state := sRun
  }.elsewhen(state === sRun && core.io.commit.valid) {
    iteration := completed
    when(core.io.commit.bits.converged || completed === config.iterations.U) {
      outcome.success := core.io.commit.bits.converged
      outcome.correction := core.io.commit.bits.decision
      outcome.marginal := core.io.commit.bits.marginal
      outcome.residual := core.io.commit.bits.residual
      outcome.totalIterations := completed
      outcome.legsExecuted := 1.U
      outcome.solutionsFound := core.io.commit.bits.converged.asUInt
      state := sOutput
    }
  }.elsewhen(io.out.fire) {
    state := sIdle
  }
}
