package chipsldpc

import chipsldpc.graph.{TannerGraph, TannerNodeGraphs}
import java.nio.file.{Files, Paths}
import scala.util.Random

/** Write deterministic LLR-derived stimuli and pure-Scala expected results. */
object StaticGolden {
  private val graph = TannerGraph.fromRows(
    7,
    Seq(Seq(3, 4, 5, 6), Seq(1, 2, 5, 6), Seq(0, 2, 4, 6)),
  )
  private val nodes = TannerNodeGraphs.from(graph)

  private def packed(bits: Seq[Boolean]): Int =
    bits.zipWithIndex.foldLeft(0) { case (word, (bit, i)) => word | (if (bit) 1 << i else 0) }

  private[chipsldpc] def prior(probability: Double): Int = {
    require(probability > 0.0 && probability < 0.5)
    val maximum = (1 << RelayDefaults.q.magnitudeBits) - 1
    math.round(RelayDefaults.priorScale * math.log((1.0 - probability) / probability)).toInt.max(0).min(maximum)
  }

  def main(args: Array[String]): Unit = {
    require(args.nonEmpty, "usage: StaticGolden <output> [prior-sets] [iterations] [seed]")
    val output = Paths.get(args(0))
    val priorSets = args.lift(1).fold(32)(_.toInt)
    val iterations = args.lift(2).fold(4)(_.toInt)
    val seed = args.lift(3).fold(0L)(_.toLong)
    require(priorSets > 0 && iterations > 0 && iterations < 8)

    val random = new Random(seed)
    val text = new StringBuilder
    for (_ <- 0 until priorSets) {
      val priors = Vector.fill(graph.variableCount) {
        val logP = math.log(1e-4) + random.nextDouble() * math.log(0.2 / 1e-4)
        prior(math.exp(logP))
      }
      for (word <- 0 until (1 << graph.checkCount)) {
        val syndrome = Vector.tabulate(graph.checkCount)(i => ((word >> i) & 1) != 0)
        var state = Reference.initialize(nodes, priors, RelayDefaults.q)
        for (iteration <- 1 to iterations) {
          state = Reference.iterate(
            nodes, state, syndrome, priors, iteration, RelayDefaults.q, RelayDefaults.scale,
          )
          val residual = Reference.residual(nodes, state, syndrome)
          val fields = Seq(word) ++ priors ++ Seq(iteration) ++ state.marginal ++ Seq(
            packed(state.decision), packed(residual), if (residual.contains(true)) 0 else 1,
          )
          text.append(fields.mkString(" ")).append('\n')
        }
      }
    }
    Option(output.getParent).foreach(Files.createDirectories(_))
    Files.writeString(output, text.result())
    println(s"wrote ${priorSets * (1 << graph.checkCount) * iterations} golden records to $output")
  }
}
