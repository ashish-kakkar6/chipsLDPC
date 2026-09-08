package chipsldpc

import chisel3._
import chisel3.util.{Cat, Enum, log2Ceil}
import java.nio.file.{Files, Path, Paths}

/** BB benchmark ABI around autonomous early-terminating BP, with no OSD hardware. */
private final class BpOnlyArtifact(problem: DecoderProblem) extends Module {
  override def desiredName: String = "BpOnlyArtifact"
  private val graph = problem.graph
  private val q = RelayDefaults.q
  private val iterationBits = math.max(1, log2Ceil(problem.iterations + 1))
  private val indexBits = math.max(1, log2Ceil(problem.n))

  val inputValid = IO(Input(Bool()))
  val inputReady = IO(Output(Bool()))
  val syndrome = IO(Input(UInt(graph.checkCount.W)))
  val prior = IO(Input(UInt((problem.n * q.magnitudeBits).W)))
  val scopeValid = IO(Input(Bool()))
  val scope = IO(Input(UInt(problem.n.W)))
  val correctionValid = IO(Output(Bool()))
  val correctionReady = IO(Input(Bool()))
  val correctionIndex = IO(Output(UInt(indexBits.W)))
  val correctionValue = IO(Output(Bool()))
  val correctionLast = IO(Output(Bool()))
  val resultValid = IO(Output(Bool()))
  val resultReady = IO(Input(Bool()))
  val status = IO(Output(UInt(2.W)))
  val completedIterations = IO(Output(UInt(iterationBits.W)))
  val cycles = IO(Output(UInt(32.W)))
  val bpCycles = IO(Output(UInt((iterationBits + 1).W)))
  val osdCycles = IO(Output(UInt(32.W)))
  val selected = IO(Output(UInt(1.W)))
  val activeRows = IO(Output(UInt(1.W)))
  val solverCycles = IO(Output(UInt(32.W)))
  val softOutput = IO(Output(UInt((problem.n * q.accumulatorBits).W)))

  private val sIdle :: sBp :: sOutput :: sResult :: Nil = Enum(4)
  private val state = RegInit(sIdle)
  private val iteration = RegInit(0.U(iterationBits.W))
  private val outputIndex = RegInit(0.U(indexBits.W))
  private val decision = Reg(Vec(problem.n, Bool()))
  private val converged = RegInit(false.B)
  private val cycleCount = RegInit(0.U(32.W))
  private val bp = Module(new StaticTannerDatapath(problem.nodes))
  private val completed = iteration + 1.U
  private val stopBp = bp.io.result.valid &&
    (bp.io.result.bits.converged || completed === problem.iterations.U)
  private val requested = iteration + 1.U + bp.io.result.valid.asUInt
  private val controlMax = (BigInt(1) << RelayDefaults.scale.controlBits) - 1

  bp.io.load.valid := state === sIdle && inputValid
  bp.io.load.bits.syndrome.zipWithIndex.foreach { case (bit, i) => bit := syndrome(i) }
  bp.io.load.bits.prior.zipWithIndex.foreach { case (value, i) =>
    value := prior((i + 1) * q.magnitudeBits - 1, i * q.magnitudeBits)
  }
  bp.io.step.valid := state === sBp && !stopBp
  bp.io.step.bits := Mux(requested > controlMax.U, controlMax.U, requested)(
    RelayDefaults.scale.controlBits - 1, 0,
  )

  inputReady := state === sIdle && bp.io.load.ready
  correctionValid := state === sOutput
  correctionIndex := outputIndex
  correctionValue := decision(outputIndex)
  correctionLast := outputIndex === (problem.n - 1).U
  resultValid := state === sResult
  status := Mux(converged, 0.U, 2.U)
  completedIterations := iteration
  cycles := cycleCount
  bpCycles := iteration << 1
  osdCycles := 0.U
  selected := 0.U
  activeRows := 0.U
  solverCycles := 0.U
  softOutput := Cat(bp.io.result.bits.marginal.reverse.map(_.asUInt))

  when(inputValid && inputReady) {
    iteration := 0.U
    converged := false.B
    cycleCount := 0.U
    state := sBp
  }.elsewhen(state =/= sIdle && state =/= sResult) {
    cycleCount := cycleCount + 1.U
  }

  when(state === sBp && bp.io.result.valid) {
    iteration := completed
    when(stopBp) {
      decision := bp.io.result.bits.decision
      converged := bp.io.result.bits.converged
      outputIndex := 0.U
      state := sOutput
    }
  }.elsewhen(state === sOutput && correctionReady) {
    when(correctionLast) { state := sResult }
      .otherwise { outputIndex := outputIndex + 1.U }
  }.elsewhen(state === sResult && resultReady) {
    state := sIdle
  }
}

object BpOnlyExperiment {
  private def bit(value: Boolean): Int = if (value) 1 else 0

  private[chipsldpc] def artifactConfig(problem: DecoderProblem) = Seq(
    problem.graph.checkCount, problem.n, RelayDefaults.q.magnitudeBits,
    RelayDefaults.q.accumulatorBits, 0, 0,
  )

  private[chipsldpc] def golden(problem: DecoderProblem): String = {
    var state = Reference.initialize(problem.nodes, problem.prior, RelayDefaults.q)
    var iteration = 0
    var converged = false
    while (iteration < problem.iterations && !converged) {
      iteration += 1
      state = Reference.iterate(
        problem.nodes, state, problem.syndrome, problem.prior, problem.control(iteration),
        RelayDefaults.q, RelayDefaults.scale,
      )
      converged = !Reference.residual(problem.nodes, state, problem.syndrome).contains(true)
    }
    val correction = state.decision.zipWithIndex.flatMap { case (value, index) =>
      Seq(index, bit(value))
    }
    Seq(
      artifactConfig(problem), problem.syndrome.map(bit), problem.prior,
      Seq(if (converged) 0 else 2, iteration, 2 * iteration + 1 + problem.n,
          2 * iteration, 0, 0, 0, 0, 0),
      state.marginal, Seq(problem.n) ++ correction,
    ).map(_.mkString(" ")).mkString("", "\n", "\n")
  }

  private[chipsldpc] def writeGolden(problem: DecoderProblem, output: Path): Unit = {
    Files.createDirectories(output.getParent)
    Files.writeString(output, golden(problem))
  }

  def main(args: Array[String]): Unit = {
    require(args.length == 2, "usage: BpOnlyExperiment <problem.json> <output-directory>")
    val problem = DecoderProblem.read(Paths.get(args(0)))
    val output = Paths.get(args(1))
    Files.createDirectories(output.resolve("verification"))
    Files.createDirectories(output.resolve("artifact"))
    writeGolden(problem, output.resolve("verification/golden.txt"))
    Files.writeString(output.resolve("artifact/config.txt"), artifactConfig(problem).mkString(" ") + "\n")
    Files.writeString(output.resolve("artifact/config.json"), ujson.Obj(
      "schema" -> "chipsldpc.bb144-bp-only.v1",
      "iterations" -> problem.iterations,
      "decoder" -> "early_terminating_min_sum_bp",
      "message_bits" -> RelayDefaults.q.magnitudeBits,
      "soft_bits" -> RelayDefaults.q.accumulatorBits,
      "m" -> problem.graph.checkCount,
      "n" -> problem.n,
    ).render(indent = 2) + "\n")
    Generate.emitSystemVerilogFiles(
      () => new BpOnlyArtifact(problem), output.resolve("artifact/rtl"),
    )
    println(output.toAbsolutePath)
  }
}

object BpOnlySweepGolden {
  def main(args: Array[String]): Unit = {
    require(args.nonEmpty && args.length % 2 == 0,
      "usage: BpOnlySweepGolden (<problem.json> <golden.txt>)+")
    args.grouped(2).foreach { pair =>
      BpOnlyExperiment.writeGolden(
        DecoderProblem.read(Paths.get(pair(0))), Paths.get(pair(1)),
      )
    }
  }
}
