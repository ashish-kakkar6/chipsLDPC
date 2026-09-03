package chipsldpc

import java.nio.file.{Files, Paths}

/** Write reference records without re-elaborating the unchanged graph. */
object WriteGolden {
  def main(args: Array[String]): Unit = {
    require(args.nonEmpty && args.length % 2 == 0,
      "usage: WriteGolden (<problem.json> <golden.txt>)+")
    args.grouped(2).foreach { pair =>
      val output = Paths.get(pair(1))
      Files.createDirectories(output.getParent)
      Files.writeString(output, EndToEnd.golden(DecoderProblem.read(Paths.get(pair(0)))))
    }
  }
}
