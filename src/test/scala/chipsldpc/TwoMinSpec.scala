package chipsldpc

import chisel3._
import chisel3.simulator.scalatest.ChiselSim
import org.scalatest.freespec.AnyFreeSpec

final class TwoMinSpec extends AnyFreeSpec with ChiselSim {
  "two-min preserves duplicate minima" in {
    val degree = 4
    val bits = 3
    simulate(new TwoMinHarness(degree, bits)) { dut =>
      for {
        a <- 0 until (1 << bits)
        b <- 0 until (1 << bits)
        c <- 0 until (1 << bits)
        d <- 0 until (1 << bits)
      } {
        val values = Seq(a, b, c, d)
        values.zipWithIndex.foreach { case (value, i) => dut.io.inputs(i).poke(value.U) }
        val expected = Reference.twoMin(values)
        dut.io.result.first.expect(expected.first.U)
        dut.io.result.second.expect(expected.second.U)
      }
    }
  }
}
