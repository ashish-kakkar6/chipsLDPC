package chipsldpc

import chisel3.RawModule
import chipsldpc.GaussJordan.{PeCol, PeDiag, TrapezoidMesh, TrapezoidMeshConfig}
import chipsldpc.graph.{Codes, TannerNodeGraphs}
import chipsldpc.osd.{BpFilteredOsd0, BpFilteredOsd0Config}
import chipsldpc.sort.{NeighbourSorter, NeighbourSorterConfig}
import _root_.circt.stage.ChiselStage
import java.nio.file.{Files, Paths}

object Generate {
  private val systemVerilogOptions = Array(
    "-disable-all-randomization", "-strip-debug-info", "-default-layer-specialization=enable",
  )

  private[chipsldpc] def emitSystemVerilog(
      moduleName: String,
      generator: () => RawModule,
      directory: java.nio.file.Path,
  ): Unit = {
    Files.createDirectories(directory)
    Files.writeString(
      directory.resolve(s"$moduleName.sv"),
      ChiselStage.emitSystemVerilog(
        generator(),
        firtoolOpts = systemVerilogOptions,
      ),
    )
  }

  private[chipsldpc] def emitSystemVerilogFiles(
      generator: () => RawModule,
      directory: java.nio.file.Path,
  ): Unit = {
    Files.createDirectories(directory)
    ChiselStage.emitSystemVerilogFile(
      generator(), args = Array("--target-dir", directory.toString),
      firtoolOpts = systemVerilogOptions,
    )
  }

  private[chipsldpc] def emit(
      moduleName: String,
      generator: () => RawModule,
      directory: java.nio.file.Path,
  ): Unit = {
    Files.createDirectories(directory)
    Files.writeString(directory.resolve(s"$moduleName.fir.mlir"), ChiselStage.emitFIRRTLDialect(generator()))
    emitSystemVerilog(moduleName, generator, directory)
  }

  def main(args: Array[String]): Unit = {
    val q = RelayDefaults.q
    val variable = VariableConfig(3, q)
    val steane = Codes.steane
    val steaneNodes = TannerNodeGraphs.from(steane)
    val target = args.headOption.getOrElse("iteration")
    val (moduleName, generator): (String, () => RawModule) = target match {
      case "two-min"       => "TwoMin" -> (() => new TwoMin(4, q.magnitudeBits))
      case "check-valls"   => "CheckNode" -> (() => new CheckNode(CheckConfig(4, q, VallsScale(1, 2))))
      case "check-relay"   => "CheckNode" -> (() => new CheckNode(CheckConfig(4, q, RampScale(4))))
      case "variable"      => "VariableNode" -> (() => new VariableNode(variable))
      case "iteration" =>
        "MinSumIteration2x2" -> (() => new MinSumIteration2x2(q, VallsScale(1, 2)))
      case "convergence" => "ConvergenceChecker" -> (() => new ConvergenceChecker(steane))
      case "static-steane" =>
        "StaticTannerDatapath" -> (() => new StaticTannerDatapath(steaneNodes))
      case "vanilla-steane" =>
        "VanillaBpDecoder" -> (() => new VanillaBpDecoder(VanillaBpConfig(steaneNodes, 30)))
      case "relay-steane" =>
        "RelayBpDecoder" -> (() => new RelayBpDecoder(RelayBpConfig(
          steaneNodes, maximumLegs = 4,
        )))
      case "bp-filtered-osd0-steane" =>
        "BpFilteredOsd0" -> (() => new BpFilteredOsd0(BpFilteredOsd0Config(
          steaneNodes, iterations = 30, threshold = 1, prefixes = Seq(7),
        )))
      case "neighbour-sorter" =>
        "NeighbourSorter" -> (() => new NeighbourSorter(NeighbourSorterConfig(8, q.accumulatorBits, threshold = 4)))
      case "pe-col"  => "pe_col" -> (() => new PeCol)
      case "pe-diag" => "pe_diag" -> (() => new PeDiag)
      case "trapezoid-mesh" =>
        "trapeziod_mesh" -> (() => new TrapezoidMesh(
          TrapezoidMeshConfig(n = 3, liftedCols = 2, reduceHopDelay = 2),
        ))
      case other => throw new IllegalArgumentException(s"unknown top: $other")
    }
    val directory = Paths.get(args.lift(1).getOrElse(s"build/generated/$target"))
    emit(moduleName, generator, directory)
    println(directory.toAbsolutePath)
  }
}
