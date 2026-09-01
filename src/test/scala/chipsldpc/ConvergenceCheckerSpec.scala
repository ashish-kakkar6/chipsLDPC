package chipsldpc

import chisel3._
import chisel3.simulator.scalatest.ChiselSim
import chipsldpc.graph.TannerGraph
import org.scalatest.freespec.AnyFreeSpec

final class ConvergenceCheckerSpec extends AnyFreeSpec with ChiselSim {
  private val steane = TannerGraph.fromRows(
    variableCount = 7,
    rowOnes = Seq(Seq(3, 4, 5, 6), Seq(1, 2, 5, 6), Seq(0, 2, 4, 6)),
  )

  "the Steane checker exhaustively computes H * estimate + syndrome" in {
    simulateRaw(new ConvergenceChecker(steane)) { dut =>
      for {
        estimate <- 0 until (1 << steane.variableCount)
        syndrome <- 0 until (1 << steane.checkCount)
      } {
        dut.estimate.zipWithIndex.foreach { case (bit, i) => bit.poke(((estimate >> i) & 1).B) }
        dut.syndrome.zipWithIndex.foreach { case (bit, i) => bit.poke(((syndrome >> i) & 1).B) }

        val expected = steane.rowOnes.zipWithIndex.map { case (row, check) =>
          row.count(i => ((estimate >> i) & 1) != 0) % 2 != ((syndrome >> check) & 1)
        }
        dut.residual.zip(expected).foreach { case (bit, value) => bit.expect(value.B) }
        dut.converged.expect((!expected.contains(true)).B)
      }
    }
  }
}
