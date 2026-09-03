package chipsldpc

import chisel3._
import chisel3.util.Cat
import chipsldpc.graph.{TannerGraph, TannerNodeGraphs}
import java.nio.file.{Files, Path, Paths, StandardCopyOption}

/** One validated, fixed-quantization decoder experiment. */
private[chipsldpc] final case class DecoderProblem(
    schema: Int,
    n: Int,
    rowOnes: Vector[Vector[Int]],
    prior: Vector[Int],
    syndrome: Vector[Boolean],
    iterations: Int,
) {
  require(schema == 1, "unsupported problem schema")
  val graph: TannerGraph = TannerGraph.fromRows(n, rowOnes)
  val nodes: TannerNodeGraphs = TannerNodeGraphs.from(graph)
  require(nodes.checks.forall(_.degree >= 2), "check degrees must be at least two")
  require(prior.size == n, "prior length must equal n")
  require(prior.forall(p => p >= 0 && p < (1 << RelayDefaults.q.magnitudeBits)), "prior is out of range")
  require(syndrome.size == graph.checkCount, "syndrome length must equal the row count")
  require(iterations > 0, "iterations must be positive")

  def control(iteration: Int): Int =
    iteration.min((1 << RelayDefaults.scale.controlBits) - 1)
}

private[chipsldpc] object DecoderProblem {
  private val Fields = Set("schema", "n", "row_ones", "prior", "syndrome", "iterations")

  private def integer(value: ujson.Value): Int = {
    val number = value.num
    require(number.isValidInt && number == number.toInt, s"expected an integer, got $number")
    number.toInt
  }

  def parse(text: String): DecoderProblem = {
    val json = ujson.read(text)
    require(json.obj.keySet == Fields, s"expected fields: ${Fields.toSeq.sorted.mkString(", ")}")
    def vector(name: String): Vector[Int] = json(name).arr.map(integer).toVector
    val syndrome = vector("syndrome")
    require(syndrome.forall(bit => bit == 0 || bit == 1), "syndrome entries must be binary")
    DecoderProblem(
      integer(json("schema")),
      integer(json("n")),
      json("row_ones").arr.map(_.arr.map(integer).toVector).toVector,
      vector("prior"),
      syndrome.map(_ != 0),
      integer(json("iterations")),
    )
  }

  def read(path: Path): DecoderProblem = parse(Files.readString(path))
}

/** Packed, graph-independent Verilator ABI around the production static core. */
private[chipsldpc] final class StaticTannerArtifact(nodes: TannerNodeGraphs) extends Module {
  override def desiredName: String = "StaticTannerArtifact"
  private val graph = nodes.graph
  private val q = RelayDefaults.q

  val loadValid = IO(Input(Bool()))
  val loadReady = IO(Output(Bool()))
  val syndrome = IO(Input(UInt(graph.checkCount.W)))
  val prior = IO(Input(UInt((graph.variableCount * q.magnitudeBits).W)))
  val stepValid = IO(Input(Bool()))
  val stepReady = IO(Output(Bool()))
  val stepControl = IO(Input(UInt(RelayDefaults.scale.controlBits.W)))
  val resultValid = IO(Output(Bool()))
  val marginal = IO(Output(UInt((graph.variableCount * q.accumulatorBits).W)))
  val correction = IO(Output(UInt(graph.variableCount.W)))
  val residual = IO(Output(UInt(graph.checkCount.W)))
  val converged = IO(Output(Bool()))

  private val core = Module(new StaticTannerDatapath(nodes))
  core.io.load.valid := loadValid
  loadReady := core.io.load.ready
  core.io.load.bits.syndrome.zipWithIndex.foreach { case (bit, i) => bit := syndrome(i) }
  core.io.load.bits.prior.zipWithIndex.foreach { case (value, i) =>
    value := prior((i + 1) * q.magnitudeBits - 1, i * q.magnitudeBits)
  }
  core.io.step.valid := stepValid
  core.io.step.bits := stepControl
  stepReady := core.io.step.ready

  resultValid := core.io.result.valid
  marginal := Cat(core.io.result.bits.marginal.reverse.map(_.asUInt))
  correction := Cat(core.io.result.bits.decision.reverse)
  residual := Cat(core.io.result.bits.residual.reverse)
  converged := core.io.result.bits.converged
}

/** Emit one specialized artifact and its independent per-iteration golden records. */
object EndToEnd {
  private def bit(value: Boolean): Int = if (value) 1 else 0

  private[chipsldpc] def golden(problem: DecoderProblem): String = {
    val q = RelayDefaults.q
    val lines = Vector.newBuilder[String]
    lines += Seq(
      problem.graph.checkCount, problem.n, q.magnitudeBits, q.accumulatorBits,
      problem.iterations, RelayDefaults.priorScale,
    ).mkString(" ")
    lines += (problem.syndrome.map(bit) ++ problem.prior).mkString(" ")

    var state = Reference.initialize(problem.nodes, problem.prior, q)
    for (iteration <- 1 to problem.iterations) {
      val control = problem.control(iteration)
      state = Reference.iterate(
        problem.nodes, state, problem.syndrome, problem.prior,
        control, q, RelayDefaults.scale,
      )
      val residual = Reference.residual(problem.nodes, state, problem.syndrome)
      lines += (
        Seq(control) ++ state.marginal ++ state.decision.map(bit) ++
          residual.map(bit) ++ Seq(bit(!residual.contains(true)))
      ).mkString(" ")
    }
    lines.result().mkString("", "\n", "\n")
  }

  def main(args: Array[String]): Unit = {
    require(args.length == 2, "usage: EndToEnd <problem.json> <output-directory>")
    val input = Paths.get(args(0))
    val output = Paths.get(args(1))
    val problem = DecoderProblem.read(input)
    Files.createDirectories(output)
    Files.copy(input, output.resolve("problem.json"), StandardCopyOption.REPLACE_EXISTING)
    Files.writeString(output.resolve("golden.txt"), golden(problem))
    Generate.emit("StaticTannerArtifact", () => new StaticTannerArtifact(problem.nodes), output)
    println(output.toAbsolutePath)
  }
}
