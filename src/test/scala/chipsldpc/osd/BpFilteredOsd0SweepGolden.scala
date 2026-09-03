package chipsldpc.osd

import chipsldpc.DecoderProblem
import java.nio.file.{Files, Paths}

/** Write independent one-shot golden records for one artifact across a p sweep. */
object BpFilteredOsd0SweepGolden {
  def main(args: Array[String]): Unit = {
    require(args.length >= 3 && args.tail.length % 2 == 0,
      "usage: BpFilteredOsd0SweepGolden <k0,k1,...> (<problem.json> <golden.txt>)+")
    val prefixes = args.head.split(",").map(_.toInt).toSeq
    args.tail.grouped(2).foreach { pair =>
      val problem = DecoderProblem.read(Paths.get(pair(0)))
      val output = Paths.get(pair(1))
      Files.createDirectories(output.getParent)
      Files.writeString(output, BpFilteredOsd0Experiment.golden(
        problem, BpFilteredOsd0Experiment.decoderConfig(problem, prefixes),
      ))
    }
  }
}
