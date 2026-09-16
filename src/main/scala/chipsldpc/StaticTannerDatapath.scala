package chipsldpc

import chisel3._
import chisel3.util.{Decoupled, RegEnable, Valid}
import chipsldpc.graph.TannerNodeGraphs

final class StaticDecoderInput(checks: Int, variables: Int, q: Quantization) extends Bundle {
  val syndrome = Vec(checks, Bool())
  val prior = Vec(variables, UInt(q.magnitudeBits.W))
}

final class StaticDecoderResult(checks: Int, variables: Int, q: Quantization) extends Bundle {
  val marginal = Vec(variables, SInt(q.accumulatorBits.W))
  val decision = Vec(variables, Bool())
  val residual = Vec(checks, Bool())
  val converged = Bool()
}

private[chipsldpc] final class StaticCheckStage(config: CheckConfig) extends Module {
  val io = IO(new Bundle {
    val load = Input(Bool())
    val enable = Input(Bool())
    val input = Input(Vec(config.degree, new SignMag(config.q.magnitudeBits)))
    val syndromeIn = Input(Bool())
    val scaleControl = Input(UInt(config.scale.controlBits.W))
    val syndrome = Output(Bool())
    val result = Output(new CheckResult(config))
  })

  private val syndrome = RegEnable(io.syndromeIn, io.load)
  private val core = Module(new CheckNode(config))
  core.inputs := io.input
  core.syndrome := syndrome
  core.scaleShift.foreach(_ := io.scaleControl)

  io.syndrome := syndrome
  io.result := RegEnable(core.result, io.enable)
}

private[chipsldpc] final class StaticVariableStage(config: VariableConfig) extends Module {
  val io = IO(new Bundle {
    val load = Input(Bool())
    val enable = Input(Bool())
    val restartMessages = Input(Bool())
    val input = Input(Vec(config.degree, new CheckMessage(config.q.magnitudeBits)))
    val priorIn = Input(UInt(config.q.magnitudeBits.W))
    val bias = Input(SInt(config.q.accumulatorBits.W))
    val prior = Output(UInt(config.q.magnitudeBits.W))
    val next = Output(new VariableResult(config))
    val result = Output(new VariableResult(config))
  })

  private val priorIn = io.priorIn.pad(config.q.accumulatorBits).asSInt
  private val prior = RegEnable(io.priorIn, io.load)
  private val core = Module(new VariableNode(config))
  core.inputs := io.input
  core.prior := io.bias

  private val state = Reg(new VariableResult(config))
  when(io.load) {
    state.marginal := priorIn
    state.decision := false.B
    state.extrinsic.foreach { message =>
      message.sign := false.B
      message.magnitude := io.priorIn
    }
  }.elsewhen(io.enable) {
    state.marginal := core.result.marginal
    state.decision := core.result.decision
    state.extrinsic.zip(core.result.extrinsic).foreach { case (message, next) =>
      when(io.restartMessages) {
        message.sign := false.B
        message.magnitude := prior
      }.otherwise {
        message := next
      }
    }
  }
  io.prior := prior
  io.next := core.result
  io.result := state
}

/** Shared statically wired Tanner core: one CNU cycle, then one VNU cycle. */
private[chipsldpc] final class StaticTannerCore(
    nodes: TannerNodeGraphs,
    q: Quantization = RelayDefaults.q,
    scale: CheckScale = RelayDefaults.scale,
) extends Module {
  private val graph = nodes.graph
  require(nodes.checks.forall(_.degree >= 2), "check degrees must be at least two")

  val io = IO(new Bundle {
    val load = Flipped(Decoupled(new StaticDecoderInput(graph.checkCount, graph.variableCount, q)))
    val step = Flipped(Decoupled(UInt(scale.controlBits.W)))
    val bias = Input(Vec(graph.variableCount, SInt(q.accumulatorBits.W)))
    val restartMessages = Input(Bool())
    val prior = Output(Vec(graph.variableCount, SInt(q.accumulatorBits.W)))
    val commit = Valid(new StaticDecoderResult(graph.checkCount, graph.variableCount, q))
    val result = Valid(new StaticDecoderResult(graph.checkCount, graph.variableCount, q))
  })

  private val loaded = RegInit(false.B)
  private val vnuPhase = RegInit(false.B)
  private val resultValid = RegInit(false.B)
  io.load.ready := !vnuPhase
  io.step.ready := loaded && !vnuPhase && !io.load.valid
  when(io.load.fire) { loaded := true.B }
  vnuPhase := io.step.fire
  resultValid := vnuPhase

  private val checks = nodes.checks.map { node =>
    val stage = Module(new StaticCheckStage(CheckConfig(node.degree, q, scale)))
    stage.suggestName(s"cnu_${node.checkId}")
    stage.io.load := io.load.fire
    stage.io.enable := io.step.fire
    stage.io.syndromeIn := io.load.bits.syndrome(node.checkId)
    stage.io.scaleControl := io.step.bits
    stage
  }
  private val variables = nodes.variables.map { node =>
    val stage = Module(new StaticVariableStage(VariableConfig(node.degree, q)))
    stage.suggestName(s"vnu_${node.variableId}")
    stage.io.load := io.load.fire
    stage.io.enable := vnuPhase
    stage.io.restartMessages := io.restartMessages
    stage.io.priorIn := io.load.bits.prior(node.variableId)
    stage.io.bias := io.bias(node.variableId)
    stage
  }

  nodes.connections.foreach { edge =>
    val check = checks(edge.checkId).io
    val variable = variables(edge.variableId).io
    check.input(edge.checkPort) := variable.result.extrinsic(edge.variablePort)
    variable.input(edge.variablePort).minima := check.result.minima
    variable.input(edge.variablePort).sign := check.result.edges(edge.checkPort).sign
    variable.input(edge.variablePort).useSecond := check.result.edges(edge.checkPort).useSecond
  }

  private def connectVariables(output: StaticDecoderResult, values: Seq[VariableResult]): Unit = {
    values.zipWithIndex.foreach { case (variable, id) =>
      output.marginal(id) := variable.marginal
      output.decision(id) := variable.decision
    }
  }

  variables.zipWithIndex.foreach { case (variable, id) =>
    io.prior(id) := variable.io.prior.pad(q.accumulatorBits).asSInt
  }
  private val convergence = Module(new ConvergenceChecker(graph))
  convergence.estimate := VecInit(variables.map(_.io.next.decision))
  convergence.syndrome := VecInit(checks.map(_.io.syndrome))
  io.commit.valid := vnuPhase
  connectVariables(io.commit.bits, variables.map(_.io.next))
  io.commit.bits.residual := convergence.residual
  io.commit.bits.converged := convergence.converged

  private val resultResidual = RegEnable(convergence.residual, vnuPhase)
  private val resultConverged = RegEnable(convergence.converged, vnuPhase)
  io.result.valid := resultValid
  connectVariables(io.result.bits, variables.map(_.io.result))
  io.result.bits.residual := resultResidual
  io.result.bits.converged := resultConverged
}

/** Compatibility shell exposing the original manually stepped vanilla datapath. */
final class StaticTannerDatapath(
    nodes: TannerNodeGraphs,
    q: Quantization = RelayDefaults.q,
    scale: CheckScale = RelayDefaults.scale,
) extends Module {
  private val graph = nodes.graph
  val io = IO(new Bundle {
    val load = Flipped(Decoupled(new StaticDecoderInput(graph.checkCount, graph.variableCount, q)))
    val step = Flipped(Decoupled(UInt(scale.controlBits.W)))
    val result = Valid(new StaticDecoderResult(graph.checkCount, graph.variableCount, q))
  })

  private val core = Module(new StaticTannerCore(nodes, q, scale))
  core.io.load <> io.load
  core.io.step <> io.step
  core.io.bias := core.io.prior
  core.io.restartMessages := false.B
  io.result := core.io.result
}
