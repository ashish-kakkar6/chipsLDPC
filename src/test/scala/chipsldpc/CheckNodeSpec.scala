package chipsldpc

import chisel3._
import chisel3.simulator.scalatest.ChiselSim
import org.scalatest.freespec.AnyFreeSpec

final class CheckNodeSpec extends AnyFreeSpec with ChiselSim {
  private def drive(dut: CheckNodeHarness, inputs: Seq[Reference.SignMag], syndrome: Boolean, shift: Int): Unit = {
    inputs.zipWithIndex.foreach { case (input, i) =>
      dut.io.inputs(i).sign.poke(input.sign.B)
      dut.io.inputs(i).magnitude.poke(input.magnitude.U)
    }
    dut.io.syndrome.poke(syndrome.B)
    dut.io.scaleShift.poke(shift.U)
  }

  private def expect(dut: CheckNodeHarness, expected: Reference.CheckResult): Unit = {
    dut.io.result.minima.first.expect(expected.minima.first.U)
    dut.io.result.minima.second.expect(expected.minima.second.U)
    expected.edges.zipWithIndex.foreach { case (edge, i) =>
      dut.io.result.edges(i).sign.expect(edge.sign.B)
      dut.io.result.edges(i).useSecond.expect(edge.useSecond.B)
    }
  }

  "check update is exhaustive for a small unscaled node" in {
    val config = CheckConfig(3, Quantization(2, 6))
    simulate(new CheckNodeHarness(config)) { dut =>
      for {
        a <- 0 until 4
        b <- 0 until 4
        c <- 0 until 4
        signs <- 0 until 8
        syndrome <- Seq(false, true)
      } {
        val magnitudes = Seq(a, b, c)
        val inputs = magnitudes.zipWithIndex.map { case (magnitude, i) =>
          Reference.SignMag(((signs >> i) & 1) != 0, magnitude)
        }
        drive(dut, inputs, syndrome, 0)
        expect(dut, Reference.check(inputs, syndrome, 0, config))
      }
    }
  }

  "paper scaling policies act on the shared minimum pair" in {
    val inputs = Seq(Reference.SignMag(false, 3), Reference.SignMag(true, 5), Reference.SignMag(false, 7))
    Seq[CheckScale](VallsScale(1, 2), RampScale(4)).foreach { scale =>
      val config = CheckConfig(3, Quantization(4, 8), scale)
      simulate(new CheckNodeHarness(config)) { dut =>
        val shifts = scale match {
          case _: RampScale => 0 to 4
          case _            => Seq(0)
        }
        shifts.foreach { shift =>
          drive(dut, inputs, syndrome = true, shift)
          expect(dut, Reference.check(inputs, syndrome = true, shift, config))
        }
      }
    }
  }
}
