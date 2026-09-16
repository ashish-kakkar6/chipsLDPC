package chipsldpc

import chisel3._
import chisel3.simulator.scalatest.ChiselSim
import org.scalatest.freespec.AnyFreeSpec
import scala.util.Random

final class VariableNodeSpec extends AnyFreeSpec with ChiselSim {
  private def driveMessage(port: CheckMessage, message: Reference.CheckMessage): Unit = {
    port.minima.first.poke(message.minima.first.U)
    port.minima.second.poke(message.minima.second.U)
    port.sign.poke(message.sign.B)
    port.useSecond.poke(message.useSecond.B)
  }

  private def expect(port: VariableResult, expected: Reference.VariableResult): Unit = {
    port.marginal.expect(expected.marginal.S)
    port.decision.expect(expected.decision.B)
    expected.extrinsic.zipWithIndex.foreach { case (message, i) =>
      port.extrinsic(i).sign.expect(message.sign.B)
      port.extrinsic(i).magnitude.expect(message.magnitude.U)
    }
  }

  "variable update matches an independent fixed-width model" in {
    val config = VariableConfig(3, Quantization(3, 8))
    val random = new Random(0)
    simulate(new VariableNodeHarness(config)) { dut =>
      for (_ <- 0 until 256) {
        val inputs = Seq.fill(config.degree) {
          val a = random.nextInt(8)
          val b = a + random.nextInt(8 - a)
          Reference.CheckMessage(Reference.MinPair(a, b), random.nextBoolean(), random.nextBoolean())
        }
        val prior = random.nextInt(41) - 20
        inputs.zipWithIndex.foreach { case (message, i) => driveMessage(dut.io.inputs(i), message) }
        dut.io.prior.poke(prior.S)
        expect(dut.io.result, Reference.variable(inputs, prior, config))
      }
    }
  }

  "hard decision is one only for a negative marginal" in {
    val config = VariableConfig(1, Quantization(3, 8))
    val zero = Reference.CheckMessage(Reference.MinPair(0, 0), sign = true, useSecond = true)
    simulate(new VariableNodeHarness(config)) { dut =>
      driveMessage(dut.io.inputs(0), zero)
      for (prior <- -128 until 128) {
        dut.io.prior.poke(prior.S)
        dut.io.result.decision.expect(Reference.hardDecision(prior).B)
      }
    }
  }

}
