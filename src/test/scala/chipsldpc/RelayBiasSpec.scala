package chipsldpc

import chisel3._
import chisel3.simulator.scalatest.ChiselSim
import org.scalatest.freespec.AnyFreeSpec

private final class RelayBiasHarness(q: Quantization, format: RelayFormat) extends Module {
  val io = IO(new Bundle {
    val value = Input(SInt(q.accumulatorBits.W))
    val prior = Input(SInt(q.accumulatorBits.W))
    val previous = Input(SInt(q.accumulatorBits.W))
    val beta = Input(UInt(format.betaBits.W))
    val product = Output(SInt((q.accumulatorBits + format.betaBits + 1).W))
    val bias = Output(SInt(q.accumulatorBits.W))
  })

  io.product := RelayBias.reducedMultiply(io.value, io.beta, format.fractionalBits)
  io.bias := RelayBias(io.prior, io.previous, io.beta, q, format)
}

final class RelayBiasSpec extends AnyFreeSpec with ChiselSim {
  private val q = Quantization(magnitudeBits = 4, accumulatorBits = 5)
  private val format = RelayDefaults.paperFormat
  private val wideFormat = RelayFormat(betaBits = 5, fractionalBits = 3)

  private def reducedMultiply(value: Int, beta: Int): Int = {
    val magnitude = math.abs(value)
    val unsigned = (0 until q.accumulatorBits)
      .filter(bit => ((magnitude >> bit) & 1) != 0)
      .map(bit => (beta << bit) >> format.fractionalBits)
      .sum
    if (value < 0) -unsigned else unsigned
  }

  private def clip(value: Int): Int =
    value.max(-(1 << (q.accumulatorBits - 1))).min((1 << (q.accumulatorBits - 1)) - 1)

  private def relayBias(prior: Int, previous: Int, beta: Int): Int =
    clip(reducedMultiply(prior, beta) + previous - reducedMultiply(previous, beta))

  "reduced multiplication follows Table 2 and restores the sign after truncation" in {
    val vectors = Seq(
      (15, 7, 11),
      (-15, 7, -11),
      (1, 7, 0),
      (-1, 7, 0),
      (-2, 7, -1),
      (-4, 7, -3),
      (15, 10, 18),
      (-16, 10, -20),
    )
    simulate(new RelayBiasHarness(q, format)) { dut =>
      dut.io.prior.poke(0.S)
      dut.io.previous.poke(0.S)
      vectors.foreach { case (value, beta, expected) =>
        dut.io.value.poke(value.S)
        dut.io.beta.poke(beta.U)
        dut.io.product.expect(expected.S)
      }
    }
  }

  "paper-profile bias matches an independent exhaustive model" in {
    simulate(new RelayBiasHarness(q, format)) { dut =>
      for {
        prior <- 0 to 15
        previous <- -16 to 15
        beta <- 3 to 10
      } {
        dut.io.value.poke(previous.S)
        dut.io.prior.poke(prior.S)
        dut.io.previous.poke(previous.S)
        dut.io.beta.poke(beta.U)
        dut.io.product.expect(reducedMultiply(previous, beta).S)
        dut.io.bias.expect(relayBias(prior, previous, beta).S)
      }
    }
  }

  "identity, initialization, oddness, and both saturation limits are explicit" in {
    simulate(new RelayBiasHarness(q, wideFormat)) { dut =>
      for (value <- -16 to 15) {
        dut.io.value.poke(value.S)
        dut.io.beta.poke(8.U)
        dut.io.product.expect(value.S)
      }
      for {
        value <- 0 to 15
        beta <- 0 to 31
      } {
        dut.io.value.poke((-value).S)
        dut.io.beta.poke(beta.U)
        dut.io.product.expect((-reducedMultiply(value, beta)).S)
        dut.io.prior.poke(value.S)
        dut.io.previous.poke(value.S)
        dut.io.bias.expect(value.S)
      }

      Seq(
        (15, -16, 10, 15),
        (0, 7, 28, -16),
        (0, -16, 16, 15),
        (0, -16, 0, -16),
      ).foreach { case (prior, previous, beta, expected) =>
        dut.io.prior.poke(prior.S)
        dut.io.previous.poke(previous.S)
        dut.io.beta.poke(beta.U)
        dut.io.bias.expect(expected.S)
      }
    }
  }
}
