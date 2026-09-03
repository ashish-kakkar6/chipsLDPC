package chipsldpc.osd

import chisel3._
import chisel3.util.{Decoupled, Enum, Mux1H, PopCount, PriorityEncoder, log2Ceil}
import chipsldpc.GaussJordan.{SystolicGf2Solver, SystolicGf2SolverConfig}
import chipsldpc.graph.TannerGraph
import chipsldpc.sort.{NeighbourOrder, NeighbourSorter, NeighbourSorterConfig, SignedAscending}

object OsdStatus extends ChiselEnum {
  val Solved, Inconsistent, Overflow = Value
}

final case class FilteredOsd0Config(
    graph: TannerGraph,
    softBits: Int,
    threshold: BigInt,
    prefixes: Seq[Int],
    rejectOverflow: Boolean = true,
    order: NeighbourOrder = SignedAscending,
) {
  require(prefixes.nonEmpty)
  require(prefixes.head > 0)
  require(prefixes.zip(prefixes.drop(1)).forall { case (left, right) => left < right })
  val maxSelected: Int = prefixes.last
  require(maxSelected > 0 && maxSelected <= graph.variableCount)

  val indexBits: Int = math.max(1, log2Ceil(graph.variableCount))
  val selectedBits: Int = math.max(1, log2Ceil(maxSelected + 1))
  val rowBits: Int = math.max(1, log2Ceil(graph.checkCount + 1))
  val attemptBits: Int = math.max(1, log2Ceil(prefixes.size))
  val sorter = NeighbourSorterConfig(graph.variableCount, softBits, threshold, order)
  val solverConfigs: Seq[SystolicGf2SolverConfig] =
    prefixes.map(SystolicGf2SolverConfig(_, graph.checkCount))
  val solver = SystolicGf2SolverConfig(maxSelected, graph.checkCount)
}

final class FilteredOsd0Input(config: FilteredOsd0Config) extends Bundle {
  val syndrome = Vec(config.graph.checkCount, Bool())
  val soft = Vec(config.graph.variableCount, SInt(config.softBits.W))
  val inScopeValid = Bool()
  val inScope = Vec(config.graph.variableCount, Bool())
}

final class IndexedCorrection(config: FilteredOsd0Config) extends Bundle {
  val index = UInt(config.indexBits.W)
  val value = Bool()
  val last = Bool()
}

final class FilteredOsd0Result(config: FilteredOsd0Config) extends Bundle {
  val status = OsdStatus()
  val selected = UInt(config.selectedBits.W)
  val activeRows = UInt(config.rowBits.W)
  val cycles = UInt(32.W)
  val solverCycles = UInt(32.W)
}

/** Ranked OSD-0 with progressive larger-prefix retries over one sorted frame. */
final class FilteredOsd0(config: FilteredOsd0Config) extends Module {
  val io = IO(new Bundle {
    val in = Flipped(Decoupled(new FilteredOsd0Input(config)))
    val correction = Decoupled(new IndexedCorrection(config))
    val result = Decoupled(new FilteredOsd0Result(config))
  })

  private val sIdle :: sSort :: sStart :: sRows :: sSolve :: sResult :: Nil = Enum(6)
  private val state = RegInit(sIdle)
  private val syndrome = Reg(Vec(config.graph.checkCount, Bool()))
  private val selectedIndex = Reg(Vec(config.maxSelected, UInt(config.indexBits.W)))
  private val matrix = RegInit(VecInit(Seq.fill(config.graph.checkCount)(0.U(config.maxSelected.W))))
  private val selected = RegInit(0.U(config.selectedBits.W))
  private val pendingRows = RegInit(0.U(config.graph.checkCount.W))
  private val activeRows = RegInit(0.U(config.rowBits.W))
  private val overflow = RegInit(false.B)
  private val attempt = RegInit(0.U(config.attemptBits.W))
  private val completedSolverCycles = RegInit(0.U(32.W))
  private val cycles = RegInit(0.U(32.W))
  private val immediateStatus = RegInit(OsdStatus.Solved)

  private val maxColumnDegree = config.graph.colOnes.map(_.size).max
  private val rowIndexBits = math.max(1, log2Ceil(config.graph.checkCount))
  private val columnRows = VecInit(config.graph.colOnes.map { checks =>
    VecInit(Seq.tabulate(maxColumnDegree)(i => checks.lift(i).getOrElse(0).U(rowIndexBits.W)))
  })
  private val columnValid = VecInit(config.graph.colOnes.map { checks =>
    VecInit(Seq.tabulate(maxColumnDegree)(i => (i < checks.size).B))
  })
  private val rowsByAttempt = config.prefixes.map { prefix =>
    VecInit(matrix.zip(syndrome).map { case (row, bit) =>
      row(prefix - 1, 0).orR || bit
    }).asUInt
  }
  private val nextRow = PriorityEncoder(pendingRows)

  private val sorter = Module(new NeighbourSorter(config.sorter))
  private val solvers = config.solverConfigs.map(solver => Module(new SystolicGf2Solver(solver)))
  private val activeSolver = solvers.indices.map(i => attempt === i.U)
  private val solveRows = Mux1H(activeSolver.zip(rowsByAttempt))
  private val currentPrefix = Mux1H(activeSolver.zip(
    config.prefixes.map(_.U(config.selectedBits.W)),
  ))
  private val solveCount = Mux(selected < currentPrefix, selected, currentPrefix)

  sorter.io.in.valid := io.in.valid && state === sIdle
  sorter.io.in.bits.soft := io.in.bits.soft
  sorter.io.in.bits.inScopeValid := io.in.bits.inScopeValid
  sorter.io.in.bits.inScope := io.in.bits.inScope
  sorter.io.out.ready := state === sSort

  for (i <- solvers.indices) {
    val solver = solvers(i)
    val solverConfig = config.solverConfigs(i)
    solver.io.start.valid := state === sStart && activeSolver(i)
    solver.io.start.bits.rows := PopCount(rowsByAttempt(i))
    solver.io.start.bits.activeCols := solveCount(solverConfig.activeCountBits - 1, 0)
    solver.io.row.valid := state === sRows && activeSolver(i) && pendingRows.orR
    solver.io.row.bits.coefficients := matrix(nextRow)(config.prefixes(i) - 1, 0)
    solver.io.row.bits.rhs := syndrome(nextRow)
    solver.io.solution.ready := state === sSolve && activeSolver(i) && io.correction.ready
  }

  private val solverStartFire = solvers.map(_.io.start.fire).reduce(_ || _)
  private val solverRowFire = solvers.map(_.io.row.fire).reduce(_ || _)
  private val solverSolutionValid = Mux1H(activeSolver.zip(solvers.map(_.io.solution.valid)))
  private val solverSolutionSlot = Mux1H(activeSolver.zip(
    solvers.map(_.io.solution.bits.slot.pad(config.solver.slotBits)),
  ))
  private val solverSolutionValue = Mux1H(activeSolver.zip(solvers.map(_.io.solution.bits.value)))
  private val solverSolutionLast = Mux1H(activeSolver.zip(solvers.map(_.io.solution.bits.last)))
  private val solverResultValid = Mux1H(activeSolver.zip(solvers.map(_.io.result.valid)))
  private val solverConsistent = Mux1H(activeSolver.zip(solvers.map(_.io.result.bits.consistent)))
  private val solverCycles = Mux1H(activeSolver.zip(solvers.map(_.io.result.bits.cycles.pad(32))))
  private val canRetry = attempt =/= (config.prefixes.size - 1).U && selected > currentPrefix
  private val retry = state === sSolve && solverResultValid && !solverConsistent && canRetry
  for (i <- solvers.indices)
    solvers(i).io.result.ready := state === sSolve && activeSolver(i) && (retry || io.result.ready)

  io.in.ready := state === sIdle && sorter.io.in.ready
  io.correction.valid := state === sSolve && solverSolutionValid
  io.correction.bits.index := selectedIndex(solverSolutionSlot)
  io.correction.bits.value := solverSolutionValue
  io.correction.bits.last := solverSolutionLast
  io.result.valid := state === sResult || (state === sSolve && solverResultValid && !retry)
  io.result.bits.status := Mux(
    state === sResult,
    immediateStatus,
    Mux(solverConsistent, OsdStatus.Solved, OsdStatus.Inconsistent),
  )
  io.result.bits.selected := solveCount
  io.result.bits.activeRows := activeRows
  io.result.bits.cycles := cycles
  io.result.bits.solverCycles := completedSolverCycles + Mux(state === sSolve, solverCycles, 0.U)

  when(io.in.fire) {
    syndrome := io.in.bits.syndrome
    matrix.foreach(_ := 0.U)
    selected := 0.U
    activeRows := 0.U
    overflow := false.B
    attempt := 0.U
    completedSolverCycles := 0.U
    cycles := 0.U
    state := sSort
  }.elsewhen(state =/= sIdle && !io.result.valid) {
    cycles := cycles + 1.U
  }

  when(state === sSort && sorter.io.out.fire) {
    when(selected < config.maxSelected.U) {
      val slot = selected(config.solver.slotBits - 1, 0)
      selectedIndex(slot) := sorter.io.out.bits.index
      for (edge <- 0 until maxColumnDegree) {
        val row = columnRows(sorter.io.out.bits.index)(edge)
        when(columnValid(sorter.io.out.bits.index)(edge)) {
          matrix(row) := matrix(row).bitSet(slot, true.B)
        }
      }
      selected := selected + 1.U
    }.otherwise {
      overflow := true.B
    }
  }

  when(state === sSort && sorter.io.done) {
    activeRows := PopCount(rowsByAttempt.head)
    when(overflow && config.rejectOverflow.B) {
      immediateStatus := OsdStatus.Overflow
      state := sResult
    }.otherwise {
      state := sStart
    }
  }.elsewhen(state === sStart && solverStartFire) {
    pendingRows := solveRows
    state := Mux(solveRows.orR, sRows, sSolve)
  }.elsewhen(state === sRows && solverRowFire) {
    pendingRows := pendingRows.bitSet(nextRow, false.B)
    when(PopCount(pendingRows) === 1.U) {
      state := sSolve
    }
  }.elsewhen(retry) {
    completedSolverCycles := completedSolverCycles + solverCycles
    attempt := attempt + 1.U
    for (i <- 0 until config.prefixes.size - 1)
      when(attempt === i.U) { activeRows := PopCount(rowsByAttempt(i + 1)) }
    state := sStart
  }.elsewhen(state === sSolve && io.result.fire) {
    state := sIdle
  }.elsewhen(state === sResult && io.result.fire) {
    state := sIdle
  }
}
