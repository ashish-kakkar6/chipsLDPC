package chipsldpc

import chisel3.RawModule
import chipsldpc.GaussJordan.{PeCol, PeDiag, TrapezoidMesh, TrapezoidMeshConfig}
import chipsldpc.graph.{TannerGraph, TannerNodeGraphs}
import _root_.circt.stage.ChiselStage
import java.nio.file.{Files, Paths}

object Generate {
  def main(args: Array[String]): Unit = {
    val q = RelayDefaults.q
    val variable = VariableConfig(3, q)
    val relay = RelayFormat(6, 4)
    val steane = TannerGraph.fromRows(7, Seq(Seq(3, 4, 5, 6), Seq(1, 2, 5, 6), Seq(0, 2, 4, 6)))
    val steaneNodes = TannerNodeGraphs.from(steane)
    val target = args.headOption.getOrElse("iteration")
    val (moduleName, generator): (String, () => RawModule) = target match {
      case "two-min"       => "TwoMin" -> (() => new TwoMin(4, q.magnitudeBits))
      case "check-valls"   => "CheckNode" -> (() => new CheckNode(CheckConfig(4, q, VallsScale(1, 2))))
      case "check-relay"   => "CheckNode" -> (() => new CheckNode(CheckConfig(4, q, RampScale(4))))
      case "variable"      => "VariableNode" -> (() => new VariableNode(variable))
      case "relay-variable" =>
        "RelayVariableNode" -> (() => new RelayVariableNode(variable, relay))
      case "relay-unit" =>
        "RelayVariableNodeUnit" -> (() => new RelayVariableNodeUnit(variable, relay))
      case "iteration" =>
        "MinSumIteration2x2" -> (() => new MinSumIteration2x2(q, VallsScale(1, 2)))
      case "convergence" => "ConvergenceChecker" -> (() => new ConvergenceChecker(steane))
      case "static-steane" =>
        "StaticTannerDatapath" -> (() => new StaticTannerDatapath(steaneNodes))
      case "pe-col"  => "pe_col" -> (() => new PeCol)
      case "pe-diag" => "pe_diag" -> (() => new PeDiag)
      case "trapezoid-mesh" =>
        "trapeziod_mesh" -> (() => new TrapezoidMesh(
          TrapezoidMeshConfig(n = 3, liftedCols = 2, reduceHopDelay = 2),
        ))
      case other => throw new IllegalArgumentException(s"unknown top: $other")
    }
    val directory = Paths.get(args.lift(1).getOrElse(s"build/generated/$target"))
    Files.createDirectories(directory)
    Files.writeString(directory.resolve(s"$moduleName.fir.mlir"), ChiselStage.emitFIRRTLDialect(generator()))
    Files.writeString(
      directory.resolve(s"$moduleName.sv"),
      ChiselStage.emitSystemVerilog(
        generator(),
        firtoolOpts = Array("-disable-all-randomization", "-strip-debug-info", "-default-layer-specialization=enable"),
      ),
    )
    println(directory.toAbsolutePath)
  }
}
