package chipsldpc.osd

import chisel3._
import chisel3.util.Cat
import chipsldpc.{DecoderProblem, Generate, RelayDefaults}
import chipsldpc.sort.MagnitudeAscending
import java.nio.file.{Files, Paths}

/** Packed Verilator ABI for a graph-specialized BP-filtered-OSD0 instance. */
private final class BpFilteredOsd0Artifact(config: BpFilteredOsd0Config) extends Module {
  override def desiredName: String = "BpFilteredOsd0Artifact"
  private val graph = config.graph

  val inputValid = IO(Input(Bool()))
  val inputReady = IO(Output(Bool()))
  val syndrome = IO(Input(UInt(graph.checkCount.W)))
  val prior = IO(Input(UInt((graph.variableCount * config.q.magnitudeBits).W)))
  val scopeValid = IO(Input(Bool()))
  val scope = IO(Input(UInt(graph.variableCount.W)))
  val correctionValid = IO(Output(Bool()))
  val correctionReady = IO(Input(Bool()))
  val correctionIndex = IO(Output(UInt(config.osd.indexBits.W)))
  val correctionValue = IO(Output(Bool()))
  val correctionLast = IO(Output(Bool()))
  val resultValid = IO(Output(Bool()))
  val resultReady = IO(Input(Bool()))
  val status = IO(Output(UInt(2.W)))
  val completedIterations = IO(Output(UInt(config.iterationBits.W)))
  val cycles = IO(Output(UInt(32.W)))
  val bpCycles = IO(Output(UInt((config.iterationBits + 1).W)))
  val osdCycles = IO(Output(UInt(32.W)))
  val selected = IO(Output(UInt(config.osd.selectedBits.W)))
  val activeRows = IO(Output(UInt(config.osd.rowBits.W)))
  val solverCycles = IO(Output(UInt(32.W)))
  val softOutput = IO(Output(UInt((graph.variableCount * config.q.accumulatorBits).W)))

  private val core = Module(new BpFilteredOsd0(config))
  core.io.in.valid := inputValid
  inputReady := core.io.in.ready
  core.io.in.bits.syndrome.zipWithIndex.foreach { case (bit, i) => bit := syndrome(i) }
  core.io.in.bits.prior.zipWithIndex.foreach { case (value, i) =>
    value := prior((i + 1) * config.q.magnitudeBits - 1, i * config.q.magnitudeBits)
  }
  core.io.in.bits.inScopeValid := scopeValid
  core.io.in.bits.inScope.zipWithIndex.foreach { case (bit, i) => bit := scope(i) }
  correctionValid := core.io.correction.valid
  core.io.correction.ready := correctionReady
  correctionIndex := core.io.correction.bits.index
  correctionValue := core.io.correction.bits.value
  correctionLast := core.io.correction.bits.last
  resultValid := core.io.result.valid
  core.io.result.ready := resultReady
  status := core.io.result.bits.status.asUInt
  completedIterations := core.io.result.bits.iterations
  cycles := core.io.result.bits.cycles
  bpCycles := core.io.result.bits.bpCycles
  osdCycles := core.io.result.bits.osdCycles
  selected := core.io.result.bits.selected
  activeRows := core.io.result.bits.activeRows
  solverCycles := core.io.result.bits.solverCycles
  softOutput := Cat(core.io.soft.reverse.map(_.asUInt))
}

/** Emit the exact BB-scale RTL and its independent one-shot golden record. */
object BpFilteredOsd0Experiment {
  private def bit(value: Boolean): Int = if (value) 1 else 0

  private def artifactConfig(problem: DecoderProblem, config: BpFilteredOsd0Config) = Seq(
    problem.graph.checkCount, problem.n, config.q.magnitudeBits,
    config.q.accumulatorBits, config.threshold,
    config.prefixes.size,
  ) ++ config.prefixes

  private def golden(problem: DecoderProblem, config: BpFilteredOsd0Config): String = {
    val expected = BpFilteredOsd0Reference.run(config, problem.prior, problem.syndrome)
    val correction = expected.correction.flatMap { case (index, value) => Seq(index, value) }
    Seq(
      artifactConfig(problem, config),
      problem.syndrome.map(bit),
      problem.prior,
      Seq(
        expected.status, expected.iterations, expected.cycles, expected.bpCycles,
        expected.osdCycles, expected.selected, expected.activeRows,
        expected.solverCycles, expected.eligible,
      ),
      expected.soft,
      Seq(expected.correction.size) ++ correction,
    ).map(_.mkString(" ")).mkString("", "\n", "\n")
  }

  def main(args: Array[String]): Unit = {
    require(args.length >= 3,
      "usage: BpFilteredOsd0Experiment <problem.json> <output-directory> <prefix> [<prefix> ...]")
    val problem = DecoderProblem.read(Paths.get(args(0)))
    val output = Paths.get(args(1))
    val prefixes = args.drop(2).map(_.toInt).toSeq
    val allColumns = (BigInt(1) << (RelayDefaults.q.accumulatorBits - 1)) + 1
    val config = BpFilteredOsd0Config(
      problem.nodes, RelayDefaults.q, RelayDefaults.scale,
      iterations = problem.iterations, threshold = allColumns,
      prefixes = prefixes,
      rejectOverflow = false, order = MagnitudeAscending,
    )
    Files.createDirectories(output.resolve("verification"))
    Files.createDirectories(output.resolve("artifact"))
    Files.writeString(output.resolve("verification/golden.txt"), golden(problem, config))
    Files.writeString(
      output.resolve("artifact/config.txt"), artifactConfig(problem, config).mkString(" ") + "\n",
    )
    Files.writeString(output.resolve("artifact/config.json"), ujson.Obj(
      "schema" -> "chipsldpc.bb144-progressive-osd0.v1",
      "iterations" -> config.iterations,
      "ranking" -> "ascending_absolute_soft",
      "candidates" -> "all_columns",
      "threshold" -> config.threshold.toInt,
      "reject_overflow" -> config.rejectOverflow,
      "prefixes" -> ujson.Arr(config.prefixes.map(value => ujson.Num(value)): _*),
      "message_bits" -> config.q.magnitudeBits,
      "soft_bits" -> config.q.accumulatorBits,
      "m" -> config.graph.checkCount,
      "n" -> config.graph.variableCount,
    ).render(indent = 2) + "\n")
    Generate.emitSystemVerilogFiles(
      () => new BpFilteredOsd0Artifact(config), output.resolve("artifact/rtl"),
    )
    println(output.toAbsolutePath)
  }
}
