package chipsldpc.GaussJordan

import chisel3._
import chisel3.simulator.scalatest.ChiselSim
import chipsldpc.Gf2Reference
import org.scalatest.freespec.AnyFreeSpec
import scala.util.Random

final class SystolicGf2SolverSpec extends AnyFreeSpec with ChiselSim {
  private def run(
      dut: SystolicGf2Solver,
      config: SystolicGf2SolverConfig,
      rows: Vector[Int],
      rhs: Vector[Int],
      activeCols: Int,
  ): (Option[Vector[Int]], Int) = {
    val expected = Gf2Reference.solve(rows, rhs, activeCols)
    dut.io.start.valid.poke(true.B)
    dut.io.start.bits.rows.poke(rows.size.U)
    dut.io.start.bits.activeCols.poke(activeCols.U)
    dut.io.start.ready.expect(true.B)
    dut.clock.step()
    dut.io.start.valid.poke(false.B)
    dut.io.row.valid.poke(false.B)
    dut.io.solution.ready.poke(true.B)
    dut.io.result.ready.poke(true.B)
    dut.clock.step()

    rows.zip(rhs).foreach { case (row, bit) =>
      dut.io.row.ready.expect(true.B)
      dut.io.row.valid.poke(true.B)
      dut.io.row.bits.coefficients.poke(row.U)
      dut.io.row.bits.rhs.poke(bit.B)
      dut.clock.step()
    }
    dut.io.row.valid.poke(false.B)

    val actual = Vector.newBuilder[Int]
    var waited = 0
    while (!dut.io.result.valid.peek().litToBoolean && waited < 8 * config.width + 8) {
      if (dut.io.solution.valid.peek().litToBoolean) {
        actual += dut.io.solution.bits.value.peek().litValue.toInt
      }
      dut.clock.step()
      waited += 1
    }
    dut.io.result.valid.expect(true.B)
    dut.io.result.bits.consistent.expect(expected.consistent.B)
    val cycles = dut.io.result.bits.cycles.peek().litValue.toInt
    assert(cycles == (if (rows.isEmpty) 0 else rows.size + 3 * config.width + 1))
    val observed = if (expected.consistent) Some(actual.result()) else None
    observed.foreach { values =>
      assert(rows.zip(rhs).forall { case (row, bit) =>
        values.indices.foldLeft(0)((sum, col) => sum ^ (((row >> col) & 1) & values(col))) == bit
      })
      assert(values == expected.bits)
    }
    dut.clock.step()
    (observed, cycles)
  }

  "solves full-rank, rank-deficient, and inconsistent systems" in {
    val config = SystolicGf2SolverConfig(width = 4, maxRows = 6)
    simulate(new SystolicGf2Solver(config)) { dut =>
      dut.io.start.valid.poke(false.B)
      dut.io.row.valid.poke(false.B)
      dut.io.solution.ready.poke(true.B)
      dut.io.result.ready.poke(true.B)

      run(dut, config, Vector(3, 6, 12, 8), Vector(1, 0, 1, 0), activeCols = 4)
      run(dut, config, Vector(3, 6, 3), Vector(1, 0, 1), activeCols = 4)
      run(dut, config, Vector(3, 6, 3), Vector(1, 0, 0), activeCols = 4)
      run(dut, config, Vector.empty, Vector.empty, activeCols = 3)
    }
  }

  "matches GF(2) algebra for every two-column system through three rows" in {
    val config = SystolicGf2SolverConfig(width = 2, maxRows = 3)
    simulate(new SystolicGf2Solver(config)) { dut =>
      dut.io.start.valid.poke(false.B)
      dut.io.row.valid.poke(false.B)
      dut.io.solution.ready.poke(true.B)
      dut.io.result.ready.poke(true.B)
      for {
        count <- 0 to config.maxRows
        matrix <- 0 until (1 << (config.width * count))
        rhs <- 0 until (1 << count)
      } run(
        dut,
        config,
        Vector.tabulate(count)(row => matrix >> (config.width * row) & 3),
        Vector.tabulate(count)(row => rhs >> row & 1),
        activeCols = config.width,
      )
    }
  }

  "matches tall random systems" in {
    val config = SystolicGf2SolverConfig(width = 3, maxRows = 6)
    simulate(new SystolicGf2Solver(config)) { dut =>
      dut.io.start.valid.poke(false.B)
      dut.io.row.valid.poke(false.B)
      dut.io.solution.ready.poke(true.B)
      dut.io.result.ready.poke(true.B)
      val random = new Random(0x6f7364L)
      for (_ <- 0 until 256) {
        val count = random.nextInt(config.maxRows + 1)
        run(
          dut,
          config,
          Vector.fill(count)(random.nextInt(1 << config.width)),
          Vector.fill(count)(random.nextInt(2)),
          activeCols = config.width,
        )
      }
    }
  }
}
