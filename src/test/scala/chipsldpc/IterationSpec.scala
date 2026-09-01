package chipsldpc

import chisel3._
import chisel3.simulator.scalatest.ChiselSim
import org.scalatest.freespec.AnyFreeSpec

final class IterationSpec extends AnyFreeSpec with ChiselSim {
  "the fixed 2x2 graph completes one iteration in two cycles" in {
    val q = Quantization(4, 10)
    val scale = VallsScale(1, 2)
    val checkConfig = CheckConfig(2, q, scale)
    val variableConfig = VariableConfig(2, q)
    val inputs = Seq(
      Seq(Reference.SignMag(false, 3), Reference.SignMag(true, 5)),
      Seq(Reference.SignMag(false, 4), Reference.SignMag(false, 2)),
    )
    val syndrome = Seq(true, false)
    val priors = Seq(1, 1)
    val checks = inputs.zip(syndrome).map { case (messages, bit) =>
      Reference.check(messages, bit, 0, checkConfig)
    }
    val variables = (0 until 2).map { j =>
      val messages = (0 until 2).map { i =>
        Reference.CheckMessage(checks(i).minima, checks(i).edges(j).sign, checks(i).edges(j).useSecond)
      }
      Reference.variable(messages, priors(j), variableConfig)
    }

    simulate(new MinSumIteration2x2(q, scale)) { dut =>
      dut.reset.poke(true.B)
      dut.io.valid.poke(false.B)
      dut.clock.step()
      dut.reset.poke(false.B)
      inputs.zipWithIndex.foreach { case (row, i) =>
        row.zipWithIndex.foreach { case (message, j) =>
          dut.io.v2c(i)(j).sign.poke(message.sign.B)
          dut.io.v2c(i)(j).magnitude.poke(message.magnitude.U)
        }
        dut.io.syndrome(i).poke(syndrome(i).B)
        dut.io.prior(i).poke(priors(i).S)
      }
      dut.io.valid.poke(true.B)
      dut.clock.step()
      dut.io.valid.poke(false.B)
      dut.io.outValid.expect(false.B)
      dut.clock.step()
      dut.io.outValid.expect(true.B)

      variables.zipWithIndex.foreach { case (expected, j) =>
        dut.io.result(j).marginal.expect(expected.marginal.S)
        dut.io.result(j).decision.expect(expected.decision.B)
        (0 until 2).foreach { i =>
          dut.io.nextV2C(i)(j).sign.expect(expected.extrinsic(i).sign.B)
          dut.io.nextV2C(i)(j).magnitude.expect(expected.extrinsic(i).magnitude.U)
        }
      }
    }
  }
}
