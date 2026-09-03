package chipsldpc.sort

import chisel3._
import chisel3.simulator.scalatest.ChiselSim
import chipsldpc.RelayDefaults
import org.scalatest.freespec.AnyFreeSpec
import scala.util.Random

final class NeighbourSorterSpec extends AnyFreeSpec with ChiselSim {
  private val soft = Vector(-16, 2, -1, -4, 0, -3, 8, -2)

  private def expected(
      values: Vector[Int],
      config: NeighbourSorterConfig,
      scope: Option[Set[Int]],
  ): Vector[(Int, Int)] =
    values.zipWithIndex
      .collect {
        case (value, index)
            if (config.order match {
              case MagnitudeAscending => value.abs < config.threshold
              case SignedAscending => value < config.threshold
            }) && scope.forall(_.contains(index)) =>
          value -> index
      }
      .sortBy { case (value, index) =>
        (if (config.order == MagnitudeAscending) value.abs else value, index)
      }

  private def run(
      dut: NeighbourSorter,
      config: NeighbourSorterConfig,
      scope: Option[Set[Int]],
      values: Vector[Int] = soft,
      stalls: Int = 0,
  ): Int = {
    require(values.size == config.size)
    val want = expected(values, config, scope)
    dut.io.in.valid.poke(false.B)
    dut.io.out.ready.poke(true.B)
    values.zipWithIndex.foreach { case (value, index) =>
      dut.io.in.bits.soft(index).poke(value.S)
      dut.io.in.bits.inScope(index).poke(scope.exists(_.contains(index)).B)
    }
    dut.io.in.bits.inScopeValid.poke(scope.nonEmpty.B)
    dut.io.in.valid.poke(true.B)
    dut.io.in.ready.expect(true.B)
    dut.clock.step()
    dut.io.in.valid.poke(false.B)

    var cycles = 1
    for (_ <- 1 until config.size) {
      dut.io.out.valid.expect(false.B)
      dut.io.done.expect(false.B)
      dut.clock.step()
      cycles += 1
    }

    if (want.isEmpty) {
      dut.io.done.expect(true.B)
    } else {
      dut.io.out.ready.poke(false.B)
      for (_ <- 0 until stalls) {
        dut.io.out.valid.expect(true.B)
        dut.io.out.bits.soft.expect(want.head._1.S)
        dut.io.out.bits.index.expect(want.head._2.U)
        dut.clock.step()
        cycles += 1
      }
      dut.io.out.ready.poke(true.B)
      want.zipWithIndex.foreach { case ((value, index), position) =>
        dut.io.out.valid.expect(true.B)
        dut.io.out.bits.soft.expect(value.S)
        dut.io.out.bits.index.expect(index.U)
        dut.io.out.bits.last.expect((position == want.size - 1).B)
        dut.clock.step()
        cycles += 1
      }
      dut.io.done.expect(true.B)
    }

    dut.io.in.ready.expect(true.B)
    dut.clock.step()
    dut.io.done.expect(false.B)
    assert(cycles == config.size + want.size + stalls)
    cycles
  }

  "the threshold uses BP-format signed soft values and scope defaults to all" in {
    val config = NeighbourSorterConfig(soft.size, RelayDefaults.q.accumulatorBits, threshold = 4)
    simulate(new NeighbourSorter(config)) { dut =>
      assert(run(dut, config, scope = None) == config.size + 5)
      assert(run(dut, config, scope = Some(Set(2, 5, 7)), stalls = 2) == config.size + 3 + 2)
      assert(run(dut, config, scope = Some(Set.empty)) == config.size)

      val random = new Random(0x5eedL)
      for (_ <- 0 until 32) {
        val values = Vector.fill(config.size)(random.nextInt(32) - 16)
        val scope = Some((0 until config.size).filter(_ => random.nextBoolean()).toSet)
        run(dut, config, scope, values)
      }
    }
  }

  "sorting all N values takes exactly 2N active cycles" in {
    val config = NeighbourSorterConfig(soft.size, RelayDefaults.q.accumulatorBits, threshold = 17)
    simulate(new NeighbourSorter(config)) { dut =>
      assert(run(dut, config, scope = None) == 2 * config.size)
    }
  }

  "signed mode implements the strict Maurya threshold and stable LLR order" in {
    val values = Vector(-16, 2, -1, 1, 0, -3, 8, -1)
    val config = NeighbourSorterConfig(
      values.size,
      RelayDefaults.q.accumulatorBits,
      threshold = 1,
      order = SignedAscending,
    )
    simulate(new NeighbourSorter(config)) { dut =>
      assert(run(dut, config, scope = None, values = values) == config.size + 5)
      assert(run(dut, config, scope = Some(Set(2, 4, 7)), values = values) == config.size + 3)
    }
  }

  "an odd N uses one unused slot without changing the 2N contract" in {
    val values = Vector(-16, 4, -1, 0, 7)
    val config = NeighbourSorterConfig(values.size, RelayDefaults.q.accumulatorBits, threshold = 17)
    simulate(new NeighbourSorter(config)) { dut =>
      assert(run(dut, config, scope = None, values = values) == 2 * config.size)
    }

    val one = Vector(-2)
    val oneConfig = NeighbourSorterConfig(1, RelayDefaults.q.accumulatorBits, threshold = 17)
    simulate(new NeighbourSorter(oneConfig)) { dut =>
      assert(run(dut, oneConfig, scope = None, values = one) == 2)
      assert(run(dut, oneConfig, scope = Some(Set.empty), values = one) == 1)
    }
  }
}
