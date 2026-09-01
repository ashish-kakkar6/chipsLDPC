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

  "relay bias is deterministic and reuses the variable update" in {
    val config = VariableConfig(2, Quantization(4, 10))
    val format = RelayFormat(6, 4)
    val zero = Reference.CheckMessage(Reference.MinPair(0, 0), sign = true, useSecond = true)
    simulate(new RelayVariableNodeHarness(config, format)) { dut =>
      Seq((16, -8, 0), (16, -8, 16), (16, -8, 24), (-12, 20, 8)).foreach {
        case (prior, previous, beta) =>
          Seq.fill(config.degree)(zero).zipWithIndex.foreach { case (message, i) => driveMessage(dut.io.inputs(i), message) }
          dut.io.prior.poke(prior.S)
          dut.io.previous.poke(previous.S)
          dut.io.beta.poke(beta.U)
          val bias = Reference.relayBias(prior, previous, beta, format, config.q)
          dut.io.bias.expect(bias.S)
          expect(dut.io.result, Reference.variable(Seq.fill(config.degree)(zero), bias, config))
      }
    }
  }

  "the registered relay VNU carries its marginal between updates" in {
    val config = VariableConfig(2, Quantization(4, 10))
    val format = RelayFormat(6, 4)
    val negativeFour = Reference.CheckMessage(Reference.MinPair(4, 4), sign = true, useSecond = false)
    simulate(new RelayVariableNodeUnit(config, format)) { dut =>
      dut.reset.poke(true.B)
      dut.io.valid.poke(false.B)
      dut.io.initialize.poke(false.B)
      dut.clock.step()
      dut.reset.poke(false.B)
      Seq.fill(config.degree)(negativeFour).zipWithIndex.foreach { case (message, i) =>
        driveMessage(dut.io.inputs(i), message)
      }
      dut.io.prior.poke(16.S)
      dut.io.beta.poke(0.U)
      dut.io.initialize.poke(true.B)
      dut.io.valid.poke(true.B)
      dut.clock.step()
      dut.io.outValid.expect(true.B)
      dut.io.result.marginal.expect(8.S)
      dut.io.state.expect(8.S)

      dut.io.initialize.poke(false.B)
      dut.clock.step()
      dut.io.result.marginal.expect(0.S)
      dut.io.result.decision.expect(false.B)
      dut.io.state.expect(0.S)
    }
  }
}
