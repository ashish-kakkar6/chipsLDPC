package chipsldpc

import java.nio.file.{Files, Paths}

/** Emit only SystemVerilog plus independent verification data. */
object EmitSystemVerilogExperiment {
  def main(args: Array[String]): Unit = {
    require(args.length == 2, "usage: EmitSystemVerilogExperiment <problem.json> <output-directory>")
    val problem = DecoderProblem.read(Paths.get(args(0)))
    val output = Paths.get(args(1))
    val verification = output.resolve("verification")
    Files.createDirectories(verification)
    Files.writeString(verification.resolve("golden.txt"), EndToEnd.golden(problem))
    Generate.emitSystemVerilog("StaticTannerArtifact", () => new StaticTannerArtifact(problem.nodes), output.resolve("rtl"))
    println(output.toAbsolutePath)
  }
}
