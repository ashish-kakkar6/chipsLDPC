package chipsldpc

import chisel3._

/** Common controller-facing interface for replaceable Relay coefficient sources. */
final class RelayCoefficientSourceIO(variableCount: Int, betaBits: Int) extends Bundle {
  val frameStart = Input(Bool())
  val advanceLeg = Input(Bool())
  val beta = Output(Vec(variableCount, UInt(betaBits.W)))
}

abstract class RelayCoefficientSource(val variableCount: Int, val betaBits: Int) extends Module {
  val io = IO(new RelayCoefficientSourceIO(variableCount, betaBits))
}

object LfsrRelayCoefficients {
  val StateBits = 16
  val BetaBits = 4
  val InitialBeta = 7

  private val StateCount = (BigInt(1) << StateBits) - 1
  private val LaneStride = BigInt(32768)

  private[chipsldpc] def laneSeed(seedOffset: Int, lane: Int): Int = {
    require(seedOffset >= 0 && BigInt(seedOffset) < StateCount)
    require(lane >= 0)
    (1 + (BigInt(seedOffset) + BigInt(lane) * LaneStride) % StateCount).toInt
  }
}

/**
  * One deterministic 16-bit Galois LFSR per variable.
  *
  * `frameStart` and `advanceLeg` are one-cycle controller commands. A frame
  * starts at beta 7 without consuming an LFSR value. Each subsequent leg
  * consumes exactly one value, and coefficients remain stable otherwise.
  */
final class LfsrRelayCoefficients(variableCount: Int, seedOffset: Int = 0)
    extends RelayCoefficientSource(variableCount, LfsrRelayCoefficients.BetaBits) {
  import LfsrRelayCoefficients._

  require(variableCount > 0 && variableCount <= (1 << StateBits) - 1)
  require(seedOffset >= 0 && seedOffset < (1 << StateBits) - 1)

  private val seeds = Vector.tabulate(variableCount)(laneSeed(seedOffset, _))
  private val states = RegInit(VecInit(seeds.map(_.U(StateBits.W))))
  private val coefficients = RegInit(VecInit(Seq.fill(variableCount)(InitialBeta.U(BetaBits.W))))

  io.beta := coefficients

  when(io.frameStart) {
    states.zip(seeds).foreach { case (state, seed) => state := seed.U(StateBits.W) }
    coefficients.foreach(_ := InitialBeta.U)
  }.elsewhen(io.advanceLeg) {
    states.zip(coefficients).foreach { case (state, coefficient) =>
      val feedback = Mux(state(0), "hB400".U(StateBits.W), 0.U(StateBits.W))
      val nextState = (state >> 1) ^ feedback
      state := nextState
      coefficient := 3.U(BetaBits.W) + nextState(2, 0)
    }
  }
}
