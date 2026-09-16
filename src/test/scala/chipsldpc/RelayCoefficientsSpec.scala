package chipsldpc

import chisel3._
import chisel3.simulator.scalatest.ChiselSim
import org.scalatest.freespec.AnyFreeSpec

final class RelayCoefficientsSpec extends AnyFreeSpec with ChiselSim {
  private val stateCount = 65535

  private def seed(offset: Int, lane: Int): Int =
    1 + ((BigInt(offset) + BigInt(lane) * 32768) % stateCount).toInt

  private def step(state: Int): Int =
    (state >>> 1) ^ (if ((state & 1) != 0) 0xb400 else 0)

  private def expectBeta(dut: LfsrRelayCoefficients, expected: Seq[Int]): Unit =
    dut.io.beta.zip(expected).foreach { case (actual, value) => actual.expect(value.U) }

  private def reset(dut: LfsrRelayCoefficients): Unit = {
    dut.io.frameStart.poke(false.B)
    dut.io.advanceLeg.poke(false.B)
    dut.reset.poke(true.B)
    dut.clock.step()
    dut.reset.poke(false.B)
  }

  "lane seeds independently match the specified nonzero permutation" in {
    val lanes = 8784
    val offsets = Seq(0, 1, 12345, stateCount - 1)
    offsets.foreach { offset =>
      val expected = Vector.tabulate(lanes)(seed(offset, _))
      val actual = Vector.tabulate(lanes)(LfsrRelayCoefficients.laneSeed(offset, _))
      assert(actual == expected)
      assert(actual.forall(value => value >= 1 && value <= stateCount))
      assert(actual.distinct.size == lanes)
    }
  }

  "each advance matches an independent LFSR sequence and stays in the beta range" in {
    val lanes = 9
    val offset = 12345
    simulate(new LfsrRelayCoefficients(lanes, offset)) { dut =>
      reset(dut)
      expectBeta(dut, Vector.fill(lanes)(7))

      var states = Vector.tabulate(lanes)(seed(offset, _))
      for (_ <- 0 until 128) {
        states = states.map(step)
        val expected = states.map(state => 3 + (state & 7))
        dut.io.advanceLeg.poke(true.B)
        dut.clock.step()
        dut.io.advanceLeg.poke(false.B)
        expectBeta(dut, expected)
        assert(expected.forall(value => value >= 3 && value <= 10))
      }
    }
  }

  "coefficients hold between legs and every frame restarts leg zero" in {
    val lanes = 5
    val offset = 29
    val firstStates = Vector.tabulate(lanes)(lane => step(seed(offset, lane)))
    val firstBeta = firstStates.map(state => 3 + (state & 7))

    simulate(new LfsrRelayCoefficients(lanes, offset)) { dut =>
      reset(dut)

      dut.io.frameStart.poke(true.B)
      dut.io.advanceLeg.poke(true.B)
      dut.clock.step()
      dut.io.frameStart.poke(false.B)
      dut.io.advanceLeg.poke(false.B)
      expectBeta(dut, Vector.fill(lanes)(7))

      for (_ <- 0 until 4) {
        dut.clock.step()
        expectBeta(dut, Vector.fill(lanes)(7))
      }

      dut.io.advanceLeg.poke(true.B)
      dut.clock.step()
      dut.io.advanceLeg.poke(false.B)
      expectBeta(dut, firstBeta)

      for (_ <- 0 until 4) {
        dut.clock.step()
        expectBeta(dut, firstBeta)
      }

      dut.io.frameStart.poke(true.B)
      dut.clock.step()
      dut.io.frameStart.poke(false.B)
      expectBeta(dut, Vector.fill(lanes)(7))

      dut.io.advanceLeg.poke(true.B)
      dut.clock.step()
      dut.io.advanceLeg.poke(false.B)
      expectBeta(dut, firstBeta)
    }
  }
}
