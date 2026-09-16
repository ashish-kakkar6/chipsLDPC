package chipsldpc

import chisel3._
import chisel3.simulator.scalatest.ChiselSim
import org.scalatest.freespec.AnyFreeSpec

final class SparseBitmaskStreamerSpec extends AnyFreeSpec with ChiselSim {
  private val config = SparseBitmaskStreamerConfig(size = 18, bankWidth = 8)

  private def mask(indices: Seq[Int]): BigInt =
    indices.foldLeft(BigInt(0))((value, index) => value.setBit(index))

  private def reset(dut: SparseBitmaskStreamer): Unit = {
    dut.io.in.valid.poke(false.B)
    dut.io.out.ready.poke(false.B)
    dut.io.done.ready.poke(false.B)
    dut.reset.poke(true.B)
    dut.clock.step()
    dut.reset.poke(false.B)
    dut.io.in.ready.expect(true.B)
  }

  private def start(dut: SparseBitmaskStreamer, indices: Seq[Int]): Unit = {
    dut.io.in.bits.poke(mask(indices).U)
    dut.io.in.valid.poke(true.B)
    dut.io.in.ready.expect(true.B)
    dut.clock.step()
    dut.io.in.valid.poke(false.B)
  }

  private def drain(
      dut: SparseBitmaskStreamer,
      expected: Vector[Int],
      ready: Int => Boolean = _ => true,
  ): Int = {
    val received = Vector.newBuilder[Int]
    var accepted = 0
    var elapsed = 0
    var stalls = 0
    var held = Option.empty[(BigInt, Boolean)]
    while (!dut.io.done.valid.peek().litToBoolean && elapsed < 256) {
      val outputReady = ready(elapsed)
      dut.io.out.ready.poke(outputReady.B)
      val outputValid = dut.io.out.valid.peek().litToBoolean
      if (outputValid) {
        val entry = (
          dut.io.out.bits.index.peek().litValue,
          dut.io.out.bits.last.peek().litToBoolean,
        )
        held.foreach(previous => assert(entry == previous))
        if (outputReady) {
          assert(accepted < expected.size)
          assert(entry._1 == expected(accepted))
          assert(entry._2 == (accepted == expected.size - 1))
          received += entry._1.toInt
          accepted += 1
          held = None
        } else {
          held = Some(entry)
          stalls += 1
        }
      } else {
        assert(held.isEmpty)
      }
      dut.clock.step()
      elapsed += 1
    }
    assert(elapsed < 256)
    assert(received.result() == expected)
    val occupiedBanks = expected.map(_ / config.bankWidth).distinct.size
    assert(elapsed == occupiedBanks + expected.size + stalls)
    elapsed
  }

  private def finish(dut: SparseBitmaskStreamer, holdCycles: Int = 0): Unit = {
    dut.io.done.valid.expect(true.B)
    dut.io.in.ready.expect(false.B)
    for (_ <- 0 until holdCycles) {
      dut.io.out.valid.expect(false.B)
      dut.clock.step()
      dut.io.done.valid.expect(true.B)
      dut.io.in.ready.expect(false.B)
    }
    dut.io.done.ready.poke(true.B)
    dut.clock.step()
    dut.io.done.ready.poke(false.B)
    dut.io.in.ready.expect(true.B)
  }

  "streams asserted indices across bank and padding boundaries" in {
    simulate(new SparseBitmaskStreamer(config)) { dut =>
      reset(dut)
      val expected = Vector(0, 1, 7, 8, 9, 17)
      start(dut, expected)
      drain(dut, expected)
      finish(dut, holdCycles = 2)
      start(dut, Vector(8))
      drain(dut, Vector(8))
      finish(dut)
    }
  }

  "holds an entry under backpressure without rereading its input" in {
    simulate(new SparseBitmaskStreamer(config)) { dut =>
      reset(dut)
      val expected = Vector(2, 16, 17)
      start(dut, expected)
      dut.io.in.bits.poke(mask(0 until config.size).U)
      drain(dut, expected, cycle => cycle != 1 && cycle != 5)
      finish(dut)
    }
  }

  "completes an empty bitmask without emitting a placeholder" in {
    simulate(new SparseBitmaskStreamer(config)) { dut =>
      reset(dut)
      start(dut, Vector.empty)
      dut.io.out.valid.expect(false.B)
      dut.io.done.valid.expect(true.B)
      for (_ <- 0 until 3) {
        dut.clock.step()
        dut.io.out.valid.expect(false.B)
        dut.io.done.valid.expect(true.B)
        dut.io.in.ready.expect(false.B)
      }
      finish(dut)
    }
  }
}
