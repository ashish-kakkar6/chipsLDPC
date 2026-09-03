package chipsldpc.osd

import chisel3._
import chisel3.util.{Decoupled, Enum, is, log2Ceil, switch}
import chipsldpc.{CheckScale, Quantization, RelayDefaults, StaticTannerDatapath}
import chipsldpc.graph.TannerNodeGraphs
import chipsldpc.sort.{NeighbourOrder, SignedAscending}

object DecodeStatus extends ChiselEnum {
  val BpConverged, OsdSolved, OsdInconsistent, OsdOverflow = Value
}

final case class BpFilteredOsd0Config(
    nodes: TannerNodeGraphs,
    q: Quantization = RelayDefaults.q,
    scale: CheckScale = RelayDefaults.scale,
    iterations: Int = 30,
    threshold: BigInt = 1,
    prefixes: Seq[Int],
    rejectOverflow: Boolean = true,
    order: NeighbourOrder = SignedAscending,
) {
  require(iterations > 0)

  val graph = nodes.graph
  val iterationBits: Int = math.max(1, log2Ceil(iterations + 1))
  val osd = FilteredOsd0Config(
    graph, q.accumulatorBits, threshold, prefixes, rejectOverflow, order,
  )
}

final class BpFilteredOsd0Input(config: BpFilteredOsd0Config) extends Bundle {
  val syndrome = Vec(config.graph.checkCount, Bool())
  val prior = Vec(config.graph.variableCount, UInt(config.q.magnitudeBits.W))
  val inScopeValid = Bool()
  val inScope = Vec(config.graph.variableCount, Bool())
}

final class BpFilteredOsd0Result(config: BpFilteredOsd0Config) extends Bundle {
  val status = DecodeStatus()
  val iterations = UInt(config.iterationBits.W)
  val cycles = UInt(32.W)
  val bpCycles = UInt((config.iterationBits + 1).W)
  val osdCycles = UInt(32.W)
  val selected = UInt(config.osd.selectedBits.W)
  val activeRows = UInt(config.osd.rowBits.W)
  val solverCycles = UInt(32.W)
}

/** Autonomous fixed-budget BP with early convergence and filtered OSD-0 fallback. */
final class BpFilteredOsd0(config: BpFilteredOsd0Config) extends Module {
  val io = IO(new Bundle {
    val in = Flipped(Decoupled(new BpFilteredOsd0Input(config)))
    val correction = Decoupled(new IndexedCorrection(config.osd))
    val result = Decoupled(new BpFilteredOsd0Result(config))
    val soft = Output(Vec(config.graph.variableCount, SInt(config.q.accumulatorBits.W)))
  })

  private val sIdle :: sBp :: sBpOutput :: sBpResult :: sOsd :: Nil = Enum(5)
  private val state = RegInit(sIdle)
  private val syndrome = Reg(Vec(config.graph.checkCount, Bool()))
  private val inScopeValid = Reg(Bool())
  private val inScope = Reg(Vec(config.graph.variableCount, Bool()))
  private val decision = Reg(Vec(config.graph.variableCount, Bool()))
  private val iteration = RegInit(0.U(config.iterationBits.W))
  private val outputIndex = RegInit(0.U(config.osd.indexBits.W))
  private val cycles = RegInit(0.U(32.W))

  private val bp = Module(new StaticTannerDatapath(config.nodes, config.q, config.scale))
  private val osd = Module(new FilteredOsd0(config.osd))
  private val completed = iteration + 1.U
  private val stopBp = bp.io.result.valid &&
    (bp.io.result.bits.converged || completed === config.iterations.U)
  private val launchOsd = state === sBp && stopBp && !bp.io.result.bits.converged
  private val requested = iteration + 1.U + bp.io.result.valid.asUInt
  private val controlMax = (BigInt(1) << config.scale.controlBits) - 1

  bp.io.load.valid := state === sIdle && io.in.valid
  bp.io.load.bits.syndrome := io.in.bits.syndrome
  bp.io.load.bits.prior := io.in.bits.prior
  bp.io.step.valid := state === sBp && !stopBp
  bp.io.step.bits := Mux(requested > controlMax.U, controlMax.U, requested)(config.scale.controlBits - 1, 0)

  osd.io.in.valid := launchOsd
  osd.io.in.bits.syndrome := syndrome
  osd.io.in.bits.soft := bp.io.result.bits.marginal
  osd.io.in.bits.inScopeValid := inScopeValid
  osd.io.in.bits.inScope := inScope
  osd.io.correction.ready := state === sOsd && io.correction.ready
  osd.io.result.ready := state === sOsd && io.result.ready

  io.in.ready := state === sIdle && bp.io.load.ready
  io.correction.valid := Mux(state === sBpOutput, true.B, state === sOsd && osd.io.correction.valid)
  io.correction.bits.index := Mux(state === sBpOutput, outputIndex, osd.io.correction.bits.index)
  io.correction.bits.value := Mux(state === sBpOutput, decision(outputIndex), osd.io.correction.bits.value)
  io.correction.bits.last := Mux(
    state === sBpOutput,
    outputIndex === (config.graph.variableCount - 1).U,
    osd.io.correction.bits.last,
  )

  private val osdStatus = WireDefault(DecodeStatus.OsdOverflow)
  switch(osd.io.result.bits.status) {
    is(OsdStatus.Solved) { osdStatus := DecodeStatus.OsdSolved }
    is(OsdStatus.Inconsistent) { osdStatus := DecodeStatus.OsdInconsistent }
  }
  io.result.valid := state === sBpResult || (state === sOsd && osd.io.result.valid)
  io.result.bits.status := Mux(state === sBpResult, DecodeStatus.BpConverged, osdStatus)
  io.result.bits.iterations := iteration
  io.result.bits.cycles := cycles
  io.result.bits.bpCycles := iteration << 1
  io.result.bits.osdCycles := Mux(state === sOsd, osd.io.result.bits.cycles, 0.U)
  io.result.bits.selected := Mux(state === sOsd, osd.io.result.bits.selected, 0.U)
  io.result.bits.activeRows := Mux(state === sOsd, osd.io.result.bits.activeRows, 0.U)
  io.result.bits.solverCycles := Mux(state === sOsd, osd.io.result.bits.solverCycles, 0.U)
  io.soft := bp.io.result.bits.marginal

  when(io.in.fire) {
    syndrome := io.in.bits.syndrome
    inScopeValid := io.in.bits.inScopeValid
    inScope := io.in.bits.inScope
    iteration := 0.U
    cycles := 0.U
    state := sBp
  }.elsewhen(state =/= sIdle && state =/= sBpResult && !(state === sOsd && osd.io.result.valid)) {
    cycles := cycles + 1.U
  }

  when(state === sBp && bp.io.result.valid) {
    iteration := completed
    when(bp.io.result.bits.converged) {
      decision := bp.io.result.bits.decision
      outputIndex := 0.U
      state := sBpOutput
    }.elsewhen(completed === config.iterations.U) {
      assert(osd.io.in.ready)
      state := sOsd
    }
  }.elsewhen(state === sBpOutput && io.correction.fire) {
    when(io.correction.bits.last) {
      state := sBpResult
    }.otherwise {
      outputIndex := outputIndex + 1.U
    }
  }.elsewhen(state === sBpResult && io.result.fire) {
    state := sIdle
  }.elsewhen(state === sOsd && osd.io.result.fire) {
    state := sIdle
  }
}
