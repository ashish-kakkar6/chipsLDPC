package chipsldpc.GaussJordan

import chisel3._
import chisel3.simulator.scalatest.ChiselSim
import org.scalatest.freespec.AnyFreeSpec

import scala.util.Random

private object TrapezoidMeshSpec {
  final case class Inputs(
    top: BigInt = 0,
    reduce: Boolean = false,
    enable: Boolean = true,
    reset: Boolean = false,
  )

  final case class Outputs(
    bottom: BigInt,
    diagData: BigInt,
    diagReduce: BigInt,
    aState: BigInt,
    bState: BigInt,
  )
}

final class TrapezoidMeshSpec extends AnyFreeSpec with ChiselSim {
  import TrapezoidMeshSpec._

  private object Op {
    val Pass = 0
    val Swap = 1
    val Add  = 2
    val Lock = 3
  }

  /** Cycle oracle for the registered vertical, horizontal, and reduce paths. */
  private final class MeshOracle(cfg: TrapezoidMeshConfig) {
    private val rows = cfg.n
    private val cols = cfg.n + cfg.liftedCols
    private val depth = cfg.reduceHopDelay
    private var state = Array.fill(rows, cols)(false)
    private var data = Array.fill(rows, cols)(false)
    private var op = Array.fill(rows, cols)(Op.Pass)
    private var reducePipe = Array.fill(rows, depth)(false)

    private def bit(word: BigInt, index: Int): Boolean = word.testBit(index)

    private def reduceInputs(external: Boolean): Array[Boolean] =
      Array.tabulate(rows)(row => if (row == 0) external else reducePipe(row)(depth - 1))

    def step(in: Inputs): Unit = {
      if (in.reset) {
        state = Array.fill(rows, cols)(false)
        data = Array.fill(rows, cols)(false)
        op = Array.fill(rows, cols)(Op.Pass)
        reducePipe = Array.fill(rows, depth)(false)
      } else if (in.enable) {
        val reduceIn = reduceInputs(in.reduce)
        val nextState = state.map(_.clone())
        val nextData = data.map(_.clone())
        val nextOp = op.map(_.clone())
        val nextReducePipe = reducePipe.map(_.clone())

        for (row <- 0 until rows; col <- row until cols) {
          val dataIn = if (row == 0) bit(in.top, col) else data(row - 1)(col)
          if (col == row) {
            if (reduceIn(row)) {
              nextData(row)(col) = dataIn
              nextOp(row)(col) = if (state(row)(col)) Op.Swap else Op.Pass
            } else if (!dataIn) {
              nextData(row)(col) = false
              nextOp(row)(col) = Op.Pass
            } else if (!state(row)(col)) {
              nextState(row)(col) = true
              nextData(row)(col) = false
              nextOp(row)(col) = Op.Lock
            } else {
              nextData(row)(col) = false
              nextOp(row)(col) = Op.Add
            }
          } else {
            val opIn = op(row)(col - 1)
            nextOp(row)(col) = opIn
            opIn match {
              case Op.Add => nextData(row)(col) = state(row)(col) ^ dataIn
              case Op.Swap | Op.Lock =>
                nextState(row)(col) = dataIn
                nextData(row)(col) = state(row)(col)
              case _ => nextData(row)(col) = dataIn
            }
          }
        }

        for (row <- 1 until rows) {
          nextReducePipe(row)(0) = reduceIn(row - 1)
          for (stage <- 1 until depth)
            nextReducePipe(row)(stage) = reducePipe(row)(stage - 1)
        }

        state = nextState
        data = nextData
        op = nextOp
        reducePipe = nextReducePipe
      }
    }

    private def pack(width: Int)(valueAt: Int => Boolean): BigInt =
      (0 until width).foldLeft(BigInt(0)) { (word, index) =>
        if (valueAt(index)) word.setBit(index) else word
      }

    def outputs(reduce: Boolean): Outputs = {
      val a = pack(rows * rows) { index =>
        val row = index / rows
        val col = index % rows
        col >= row && state(row)(col)
      }
      val b = pack(rows * cfg.liftedCols) { index =>
        val row = index / cfg.liftedCols
        val col = index % cfg.liftedCols
        state(row)(rows + col)
      }
      Outputs(
        bottom = pack(cfg.liftedCols)(col => data(rows - 1)(rows + col)),
        diagData = pack(rows)(row => data(row)(row)),
        diagReduce = pack(rows)(row => if (row == 0) reduce else reducePipe(row)(depth - 1)),
        aState = a,
        bState = b,
      )
    }
  }

  private def expect(dut: TrapezoidMesh, expected: Outputs): Unit = {
    dut.io.data_bottom_o.expect(expected.bottom.U)
    dut.io.diag_data_out_o.expect(expected.diagData.U)
    dut.io.diag_reduce_in_o.expect(expected.diagReduce.U)
    dut.io.a_regs_flat_o.expect(expected.aState.U)
    dut.io.b_regs_flat_o.expect(expected.bState.U)
  }

  private def cycle(dut: TrapezoidMesh, oracle: MeshOracle, in: Inputs): Unit = {
    dut.io.rst.poke(in.reset.B)
    dut.io.en_i.poke(in.enable.B)
    dut.io.reduce_i.poke(in.reduce.B)
    dut.io.data_top_i.poke(in.top.U)
    dut.io.clk.step()
    oracle.step(in)
    expect(dut, oracle.outputs(in.reduce))
  }

  private def reset(dut: TrapezoidMesh, oracle: MeshOracle): Unit =
    cycle(dut, oracle, Inputs(reset = true))

  private def pack(bits: Seq[Int]): BigInt =
    bits.zipWithIndex.foldLeft(BigInt(0)) { case (word, (bit, index)) =>
      if (bit == 1) word.setBit(index) else word
    }

  "rejects empty dimensions and zero reduce delay" in {
    assertThrows[IllegalArgumentException](TrapezoidMeshConfig(0, 1, 1))
    assertThrows[IllegalArgumentException](TrapezoidMeshConfig(1, 0, 1))
    assertThrows[IllegalArgumentException](TrapezoidMeshConfig(1, 1, 0))
  }

  "N=1 has a direct diagonal and lifted boundary" in {
    val cfg = TrapezoidMeshConfig(n = 1, liftedCols = 1, reduceHopDelay = 1)
    simulateRaw(new TrapezoidMesh(cfg)) { dut =>
      val oracle = new MeshOracle(cfg)
      reset(dut, oracle)

      cycle(dut, oracle, Inputs(top = 1)) // Lock A[0,0].
      dut.io.a_regs_flat_o.expect(1.U)
      cycle(dut, oracle, Inputs(top = 2)) // Lock B[0,0] one cycle later.
      dut.io.b_regs_flat_o.expect(1.U)
      cycle(dut, oracle, Inputs(top = 1, reduce = true))
      dut.io.diag_data_out_o.expect(1.U)
      dut.io.diag_reduce_in_o.expect(1.U)
    }
  }

  "matches an independent oracle for deterministic and random traffic" in {
    val cfg = TrapezoidMeshConfig(n = 4, liftedCols = 3, reduceHopDelay = 2)
    simulateRaw(new TrapezoidMesh(cfg)) { dut =>
      val oracle = new MeshOracle(cfg)
      reset(dut, oracle)

      Seq(0x01, 0x52, 0x7f, 0x24, 0x68, 0x13).foreach { top =>
        cycle(dut, oracle, Inputs(top = BigInt(top)))
      }

      val random = new Random(0x5eedL)
      for (index <- 0 until 80) {
        val top = (0 until (cfg.n + cfg.liftedCols)).foldLeft(BigInt(0)) { (word, bit) =>
          if (random.nextBoolean()) word.setBit(bit) else word
        }
        cycle(
          dut,
          oracle,
          Inputs(top, reduce = index % 13 == 4, enable = index % 9 != 2),
        )
      }
    }
  }

  "packs A and B state row-major with coordinate zero in the LSB" in {
    val cfg = TrapezoidMeshConfig(n = 3, liftedCols = 2, reduceHopDelay = 2)
    val inputs = Seq(
      Seq(1, 0, 1, 1, 0),
      Seq(0, 1, 1, 0, 1),
      Seq(1, 1, 0, 1, 1),
      Seq(0, 0, 1, 1, 0),
      Seq(1, 0, 0, 0, 1),
      Seq(0, 1, 0, 1, 0),
    )
    simulateRaw(new TrapezoidMesh(cfg)) { dut =>
      val oracle = new MeshOracle(cfg)
      reset(dut, oracle)
      inputs.foreach(bits => cycle(dut, oracle, Inputs(top = pack(bits))))

      // A rows: 011, 110, 100; B rows: 11, 00, 10 (listed low bit first).
      dut.io.a_regs_flat_o.expect(307.U) // 0b100110011
      dut.io.b_regs_flat_o.expect(35.U)  // 0b100011
    }
  }

  "holds on disable and gives synchronous reset priority over enable" in {
    val cfg = TrapezoidMeshConfig(n = 2, liftedCols = 2, reduceHopDelay = 2)
    simulateRaw(new TrapezoidMesh(cfg)) { dut =>
      val oracle = new MeshOracle(cfg)
      reset(dut, oracle)
      cycle(dut, oracle, Inputs(top = 0xd))
      cycle(dut, oracle, Inputs(top = 0xa))
      val held = oracle.outputs(reduce = false)

      cycle(dut, oracle, Inputs(top = 0xf, reduce = true, enable = false))
      dut.io.a_regs_flat_o.expect(held.aState.U)
      dut.io.b_regs_flat_o.expect(held.bState.U)
      dut.io.data_bottom_o.expect(held.bottom.U)
      dut.io.diag_data_out_o.expect(held.diagData.U)

      // Merely asserting synchronous reset does not alter registered outputs.
      dut.io.rst.poke(true.B)
      dut.io.en_i.poke(false.B)
      dut.io.reduce_i.poke(false.B)
      expect(dut, held)
      dut.io.clk.step()
      oracle.step(Inputs(enable = false, reset = true))
      expect(dut, oracle.outputs(reduce = false))
    }
  }

  "propagates one reduce pulse through delays one, two, and three" in {
    for (delay <- 1 to 3) {
      val cfg = TrapezoidMeshConfig(n = 4, liftedCols = 1, reduceHopDelay = delay)
      simulateRaw(new TrapezoidMesh(cfg)) { dut =>
        val oracle = new MeshOracle(cfg)
        reset(dut, oracle)
        val lastArrival = ((cfg.n - 1) * delay) - 1

        for (cycleIndex <- 0 to lastArrival + 1) {
          val pulse = cycleIndex == 0
          cycle(dut, oracle, Inputs(reduce = pulse))
          val expected = (0 until cfg.n).foldLeft(BigInt(0)) { (mask, row) =>
            val visible = if (row == 0) pulse else cycleIndex == (row * delay) - 1
            if (visible) mask.setBit(row) else mask
          }
          dut.io.diag_reduce_in_o.expect(expected.U)
        }
      }
    }
  }
}
