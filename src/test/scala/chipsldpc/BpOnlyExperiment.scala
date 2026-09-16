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
  private val streamConfig = SparseBitmaskStreamerConfig(problem.n)

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

  private val sIdle :: sBp :: sOutput :: Nil = Enum(3)
  private val state = RegInit(sIdle)
  private val cycleCount = RegInit(0.U(32.W))
  private val bp = Module(new VanillaBpDecoder(VanillaBpConfig(
    problem.nodes, problem.iterations,
  )))
  private val outcome = Reg(chiselTypeOf(bp.io.out.bits))
  private val streamer = Module(new SparseBitmaskStreamer(streamConfig))

  bp.io.in.valid := state === sIdle && inputValid
  bp.io.in.bits.syndrome.zipWithIndex.foreach { case (bit, i) => bit := syndrome(i) }
  bp.io.in.bits.prior.zipWithIndex.foreach { case (value, i) =>
    value := prior((i + 1) * q.magnitudeBits - 1, i * q.magnitudeBits)
  }
  bp.io.out.ready := state === sBp && streamer.io.in.ready
  streamer.io.in.valid := state === sBp && bp.io.out.valid
  streamer.io.in.bits := bp.io.out.bits.correction.asUInt
  streamer.io.out.ready := state === sOutput && correctionReady
  streamer.io.done.ready := state === sOutput && resultReady

  inputReady := state === sIdle && bp.io.in.ready
  correctionValid := state === sOutput && streamer.io.out.valid
  correctionIndex := streamer.io.out.bits.index
  correctionValue := true.B
  correctionLast := streamer.io.out.bits.last
  resultValid := state === sOutput && streamer.io.done.valid
  status := Mux(outcome.success, 0.U, 2.U)
  completedIterations := outcome.totalIterations
  cycles := cycleCount
  bpCycles := outcome.totalIterations << 1
  osdCycles := 0.U
  selected := 0.U
  activeRows := 0.U
  solverCycles := 0.U
  softOutput := Cat(outcome.marginal.reverse.map(_.asUInt))

  when(inputValid && inputReady) {
    cycleCount := 0.U
    state := sBp
  }.elsewhen(state =/= sIdle && !resultValid) {
    cycleCount := cycleCount + 1.U
  }

  when(state === sBp && bp.io.out.fire) {
    outcome := bp.io.out.bits
    state := sOutput
  }.elsewhen(state === sOutput && streamer.io.done.fire) {
    state := sIdle
  }
}

object BpOnlyExperiment {
  private val sparseStreamAbi = 2
  private def bit(value: Boolean): Int = if (value) 1 else 0

  private[chipsldpc] def artifactConfig(problem: DecoderProblem) = Seq(
    problem.graph.checkCount, problem.n, RelayDefaults.q.magnitudeBits,
    RelayDefaults.q.accumulatorBits, 0, 0,
    sparseStreamAbi, SparseBitmaskStreamerConfig(problem.n).bankWidth,
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
    val streamConfig = SparseBitmaskStreamerConfig(problem.n)
    val correctionIndices = state.decision.zipWithIndex.collect { case (true, index) => index }
    val occupiedBanks = correctionIndices.map(_ / streamConfig.bankWidth).distinct.size
    val correction = correctionIndices.flatMap(index => Seq(index, 1))
    Seq(
      artifactConfig(problem), problem.syndrome.map(bit), problem.prior,
      Seq(if (converged) 0 else 2, iteration,
          2 * iteration + 1 + occupiedBanks + correctionIndices.size,
          2 * iteration, 0, 0, 0, 0, 0),
      state.marginal, Seq(correctionIndices.size) ++ correction,
    ).map(_.mkString(" ")).mkString("", "\n", "\n")
  }

  private[chipsldpc] def writeGolden(problem: DecoderProblem, output: Path): Unit = {
    Files.createDirectories(output.getParent)
    Files.writeString(output, golden(problem))
  }

  def main(args: Array[String]): Unit = {
    require(args.length == 2, "usage: BpOnlyExperiment <problem.json> <output-directory>")
    val problem = DecoderProblem.read(Paths.get(args(0)))
    val streamConfig = SparseBitmaskStreamerConfig(problem.n)
    val output = Paths.get(args(1))
    Files.createDirectories(output.resolve("verification"))
    Files.createDirectories(output.resolve("artifact"))
    writeGolden(problem, output.resolve("verification/golden.txt"))
    Files.writeString(output.resolve("artifact/config.txt"), artifactConfig(problem).mkString(" ") + "\n")
    Files.writeString(output.resolve("artifact/config.json"), ujson.Obj(
      "schema" -> "chipsldpc.bb144-bp-only.v2",
      "iterations" -> problem.iterations,
      "decoder" -> "early_terminating_min_sum_bp",
      "correction_stream_abi" -> sparseStreamAbi,
      "correction_stream" -> "ascending_sparse_ones",
      "correction_bank_width" -> streamConfig.bankWidth,
      "empty_correction" -> "zero stream entries; resultValid completes the frame",
      "cycle_formula" -> "2*completed_iterations+1+occupied_banks+correction_weight",
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
