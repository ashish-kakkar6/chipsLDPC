package chipsldpc

import chisel3._
import chipsldpc.graph.TannerGraph

/** Combinational residual H * estimate + syndrome over GF(2). */
final class ConvergenceChecker(graph: TannerGraph) extends RawModule {
  val estimate  = IO(Input(Vec(graph.variableCount, Bool())))
  val syndrome  = IO(Input(Vec(graph.checkCount, Bool())))
  val residual  = IO(Output(Vec(graph.checkCount, Bool())))
  val converged = IO(Output(Bool()))

  residual.zipWithIndex.foreach { case (bit, check) =>
    val parity = VecInit(graph.rowOnes(check).map(estimate(_))).asUInt.xorR
    bit := parity ^ syndrome(check)
  }
  converged := !residual.asUInt.orR
}
