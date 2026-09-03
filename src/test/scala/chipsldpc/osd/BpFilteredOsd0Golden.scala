package chipsldpc.osd

import chipsldpc.graph.{TannerGraph, TannerNodeGraphs}
import java.nio.file.{Files, Paths}

/** Write independent BP/GF(2) golden records for the emitted Steane artifact. */
object BpFilteredOsd0Golden {
  private val graph = TannerGraph.fromRows(
    7,
    Seq(Seq(3, 4, 5, 6), Seq(1, 2, 5, 6), Seq(0, 2, 4, 6)),
  )
  private val nodes = TannerNodeGraphs.from(graph)
  private val iterations = 30
  private val threshold = 1
  private val config = BpFilteredOsd0Config(
    nodes, iterations = iterations, threshold = threshold,
    prefixes = Seq(7),
  )

  private def record(priors: Vector[Int], syndrome: Int, scope: Option[Set[Int]]): Seq[Int] = {
    val syndromeBits = Vector.tabulate(graph.checkCount)(row => (syndrome & 1 << row) != 0)
    val expected = BpFilteredOsd0Reference.run(config, priors, syndromeBits, scope)
    val indices = expected.correction.map(_._1)
    val correction = expected.correction.foldLeft(0) { case (word, (index, bit)) =>
      word | bit << index
    }
    val solutions = if (indices.nonEmpty) Vector(correction) else Vector.empty
    Seq(syndrome, if (scope.nonEmpty) 1 else 0, scope.fold(0)(_.foldLeft(0)(_ | 1 << _))) ++ priors ++ Seq(
      expected.status, expected.iterations, expected.cycles, expected.bpCycles, expected.osdCycles,
      expected.selected, expected.activeRows, expected.solverCycles, indices.size,
    ) ++ indices ++ Seq(solutions.size) ++ solutions
  }

  def main(args: Array[String]): Unit = {
    require(args.length == 1, "usage: BpFilteredOsd0Golden <output>")
    val records = Vector(
      record(Vector.fill(7)(2), syndrome = 0, scope = None),
      record(Vector.fill(7)(0), syndrome = 5, scope = None),
      record(Vector.fill(7)(0), syndrome = 7, scope = Some(Set(0, 1, 3))),
      record(Vector.fill(7)(0), syndrome = 1, scope = Some(Set(0))),
      record(Vector.fill(7)(0), syndrome = 1, scope = Some(Set(6))),
    )
    val output = Paths.get(args.head)
    Option(output.getParent).foreach(Files.createDirectories(_))
    Files.writeString(output, records.map(_.mkString(" ")).mkString(s"${records.size}\n", "\n", "\n"))
  }
}
