package chipsldpc.GaussJordan

import chisel3._
import chisel3.util.{Decoupled, Enum, log2Ceil}

final case class SystolicGf2SolverConfig(width: Int, maxRows: Int) {
  require(width > 0, "width must be positive")
  require(maxRows > 0, "maxRows must be positive")

  val rowCountBits: Int = math.max(1, log2Ceil(maxRows + 1))
  val slotBits: Int = math.max(1, log2Ceil(width))
  val activeCountBits: Int = math.max(1, log2Ceil(width + 1))
  val cycleBits: Int = math.max(1, log2Ceil(maxRows + 3 * width + 3))
}

final class SystolicGf2Start(config: SystolicGf2SolverConfig) extends Bundle {
  val rows = UInt(config.rowCountBits.W)
  val activeCols = UInt(config.activeCountBits.W)
}

final class SystolicGf2Row(config: SystolicGf2SolverConfig) extends Bundle {
  val coefficients = UInt(config.width.W)
  val rhs = Bool()
}

final class SystolicGf2Bit(config: SystolicGf2SolverConfig) extends Bundle {
  val slot = UInt(config.slotBits.W)
  val value = Bool()
  val last = Bool()
}

final class SystolicGf2Result(config: SystolicGf2SolverConfig) extends Bundle {
  val consistent = Bool()
  val cycles = UInt(config.cycleBits.W)
}

/** Framed row-stream wrapper around the binary trapezoid mesh. */
final class SystolicGf2Solver(config: SystolicGf2SolverConfig) extends Module {
  val io = IO(new Bundle {
    val start = Flipped(Decoupled(new SystolicGf2Start(config)))
    val row = Flipped(Decoupled(new SystolicGf2Row(config)))
    val solution = Decoupled(new SystolicGf2Bit(config))
    val result = Decoupled(new SystolicGf2Result(config))
  })

  private val sIdle :: sClear :: sFeed :: sRun :: sOutput :: sResult :: Nil = Enum(6)
  private val state = RegInit(sIdle)
  private val rowCount = Reg(UInt(config.rowCountBits.W))
  private val activeCols = Reg(UInt(config.activeCountBits.W))
  private val rowsSeen = RegInit(0.U(config.rowCountBits.W))
  private val postCycle = RegInit(0.U(log2Ceil(3 * config.width + 2).W))
  private val cycles = RegInit(0.U(config.cycleBits.W))
  private val inconsistent = RegInit(false.B)
  private val solution = RegInit(VecInit(Seq.fill(config.width)(false.B)))
  private val outputSlot = RegInit(0.U(config.slotBits.W))

  private val mesh = Module(new TrapezoidMesh(
    TrapezoidMeshConfig(
      config.width, liftedCols = 1, reduceHopDelay = 3, exposeFullState = false,
    ),
  ))
  mesh.io.clk := clock
  mesh.io.rst := reset.asBool || state === sClear
  mesh.io.en_i := state =/= sIdle
  mesh.io.reduce_i := state === sRun && postCycle === 1.U

  private val inputBits = Wire(Vec(config.width + 1, Bool()))
  for (col <- 0 until config.width) {
    val source = activeCols - 1.U - col.U
    inputBits(col) := col.U < activeCols &&
      io.row.bits.coefficients(source(config.slotBits - 1, 0)) && io.row.fire
  }
  inputBits(config.width) := io.row.bits.rhs && io.row.fire

  private val staggered = Seq.tabulate(config.width + 1) { col =>
    RegInit(VecInit(Seq.fill(col + 1)(false.B)))
  }
  for ((pipe, col) <- staggered.zipWithIndex) {
    when(state === sClear) {
      pipe.foreach(_ := false.B)
    }.otherwise {
      pipe.head := inputBits(col)
      for (stage <- 1 until pipe.length)
        pipe(stage) := pipe(stage - 1)
    }
  }
  mesh.io.data_top_i := VecInit(staggered.map(_.last)).asUInt

  io.start.ready := state === sIdle
  io.row.ready := state === sFeed
  io.solution.valid := state === sOutput && !inconsistent && activeCols =/= 0.U
  io.solution.bits.slot := outputSlot
  io.solution.bits.value := solution((activeCols - 1.U - outputSlot)(config.slotBits - 1, 0))
  io.solution.bits.last := outputSlot === activeCols - 1.U
  io.result.valid := state === sResult
  io.result.bits.consistent := !inconsistent
  io.result.bits.cycles := cycles

  when(io.start.fire) {
    assert(io.start.bits.rows <= config.maxRows.U)
    assert(io.start.bits.activeCols <= config.width.U)
    rowCount := io.start.bits.rows
    activeCols := io.start.bits.activeCols
    rowsSeen := 0.U
    postCycle := 0.U
    cycles := 0.U
    inconsistent := false.B
    solution.foreach(_ := false.B)
    outputSlot := 0.U
    state := sClear
  }.elsewhen(state === sClear) {
    state := Mux(rowCount === 0.U, sOutput, sFeed)
  }.elsewhen(state === sFeed) {
    cycles := cycles + 1.U
    when(mesh.io.data_bottom_o(0)) {
      inconsistent := true.B
    }
    when(io.row.fire) {
      rowsSeen := rowsSeen + 1.U
      when(rowsSeen + 1.U === rowCount) {
        postCycle := 0.U
        state := sRun
      }
    }
  }.elsewhen(state === sRun) {
    cycles := cycles + 1.U
    when(postCycle <= (2 * config.width).U && mesh.io.data_bottom_o(0)) {
      inconsistent := true.B
    }
    when(postCycle > (2 * config.width).U) {
      val slot = (postCycle - (2 * config.width + 1).U)(config.slotBits - 1, 0)
      val pivot = mesh.io.diag_state_o(slot)
      solution(slot) := mesh.io.data_bottom_o(0) && pivot
    }
    when(postCycle === (3 * config.width).U) {
      outputSlot := 0.U
      state := sOutput
    }.otherwise {
      postCycle := postCycle + 1.U
    }
  }.elsewhen(state === sOutput) {
    when(inconsistent || activeCols === 0.U) {
      state := sResult
    }.elsewhen(io.solution.fire) {
      when(io.solution.bits.last) {
        state := sResult
      }.otherwise {
        outputSlot := outputSlot + 1.U
      }
    }
  }.elsewhen(io.result.fire) {
    state := sIdle
  }
}
