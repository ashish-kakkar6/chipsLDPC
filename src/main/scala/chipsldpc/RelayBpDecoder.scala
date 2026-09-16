package chipsldpc

import chisel3._
import chisel3.util.{Decoupled, Enum, Valid}
import chipsldpc.graph.TannerNodeGraphs

final case class RelayBpConfig(
    nodes: TannerNodeGraphs,
    initialIterations: Int = 80,
    relayIterations: Int = 60,
    maximumLegs: Int = 600,
    solutionTarget: Int = 1,
    seedOffset: Int = 0,
    q: Quantization = RelayDefaults.paperQ,
    scale: CheckScale = RampScale(RelayDefaults.paperQ.magnitudeBits),
    format: RelayFormat = RelayDefaults.paperFormat,
) {
  require(initialIterations > 0 && relayIterations > 0)
  require(maximumLegs > 0, "maximumLegs includes the initial leg")
  require(solutionTarget > 0)
  require(seedOffset >= 0 && seedOffset < 65535)
  require(format.betaBits == LfsrRelayCoefficients.BetaBits)

  val graph = nodes.graph
  private val maximumIterationsBig =
    BigInt(initialIterations) + BigInt(maximumLegs - 1) * relayIterations
  require(maximumIterationsBig <= RelayBpConfig.MaximumIterations)
  val maximumIterations: Int = maximumIterationsBig.toInt
  val iterationBits: Int = maximumIterationsBig.bitLength.max(1)
  val localIterationBits: Int = BigInt(initialIterations.max(relayIterations)).bitLength.max(1)
  val legBits: Int = BigInt(maximumLegs).bitLength.max(1)
  val solutionBits: Int = BigInt(solutionTarget).bitLength.max(1)
  val scoreBits: Int = (
    BigInt(graph.variableCount) * ((BigInt(1) << q.magnitudeBits) - 1)
  ).bitLength.max(1)
}

object RelayBpConfig {
  val MaximumIterations = 1000000000
}

/** Non-blocking trace emitted once at the terminal VNU commit of every Relay leg. */
final class RelayLegTrace(legBits: Int, iterationBits: Int) extends Bundle {
  val index = UInt(legBits.W)
  val iterations = UInt(iterationBits.W)
  val converged = Bool()
}

/** Relay-BP-S with persistent marginals and freshly initialized edge messages per leg. */
final class RelayBpDecoder(
    config: RelayBpConfig,
    coefficientFactory: Option[() => RelayCoefficientSource] = None,
) extends Module {
  val io = IO(new Bundle {
    val in = Flipped(Decoupled(new StaticDecoderInput(
      config.graph.checkCount, config.graph.variableCount, config.q,
    )))
    val out = Decoupled(new BpDecoderResult(
      config.graph.checkCount, config.graph.variableCount, config.q,
      config.iterationBits, config.legBits, config.solutionBits,
    ))
    val legTrace = Valid(new RelayLegTrace(config.legBits, config.localIterationBits))
  })

  private val sIdle :: sRun :: sOutput :: Nil = Enum(3)
  private val state = RegInit(sIdle)
  private val leg = RegInit(0.U(config.legBits.W))
  private val localIteration = RegInit(0.U(config.localIterationBits.W))
  private val totalIterations = RegInit(0.U(config.iterationBits.W))
  private val solutions = RegInit(0.U(config.solutionBits.W))
  private val haveBest = RegInit(false.B)
  private val bestScore = Reg(UInt(config.scoreBits.W))
  private val bestCorrection = Reg(Vec(config.graph.variableCount, Bool()))
  private val outcome = Reg(chiselTypeOf(io.out.bits))

  private val core = Module(new StaticTannerCore(config.nodes, config.q, config.scale))
  private val coefficients = Module(coefficientFactory match {
    case Some(make) => make()
    case None => new LfsrRelayCoefficients(config.graph.variableCount, config.seedOffset)
  })
  require(coefficients.variableCount == config.graph.variableCount)
  require(coefficients.betaBits == config.format.betaBits)

  core.io.load.valid := state === sIdle && io.in.valid
  core.io.load.bits := io.in.bits
  core.io.bias.zipWithIndex.foreach { case (bias, i) =>
    bias := RelayBias(
      core.io.prior(i), core.io.result.bits.marginal(i), coefficients.io.beta(i),
      config.q, config.format,
    )
  }

  private val legBudget = Mux(
    leg === 0.U, config.initialIterations.U, config.relayIterations.U,
  )
  private val completedLocal = localIteration + 1.U
  private val completedTotal = totalIterations + 1.U
  private val controlMax = (BigInt(1) << config.scale.controlBits) - 1
  core.io.step.valid := state === sRun
  core.io.step.bits := Mux(completedLocal > controlMax.U, controlMax.U, completedLocal)(
    config.scale.controlBits - 1, 0,
  )

  private val scoreTerms = core.io.prior.zip(core.io.commit.bits.decision).map {
    case (prior, selected) =>
      Mux(selected, prior.asUInt.pad(config.scoreBits), 0.U(config.scoreBits.W))
  }
  private val candidateScore = Arithmetic.sumUnsigned(scoreTerms, config.scoreBits)
  private val candidateWins = core.io.commit.bits.converged &&
    (!haveBest || candidateScore < bestScore)
  private val nextSolutions = solutions + core.io.commit.bits.converged.asUInt
  private val legDone = core.io.commit.bits.converged || completedLocal === legBudget
  private val targetReached = core.io.commit.bits.converged &&
    nextSolutions >= config.solutionTarget.U
  private val hasNextLeg = leg < (config.maximumLegs - 1).U
  private val advanceLeg = state === sRun && core.io.commit.valid && legDone &&
    hasNextLeg && !targetReached

  core.io.restartMessages := advanceLeg
  coefficients.io.frameStart := io.in.fire
  coefficients.io.advanceLeg := advanceLeg

  io.legTrace.valid := state === sRun && core.io.commit.valid && legDone
  io.legTrace.bits.index := leg
  io.legTrace.bits.iterations := completedLocal
  io.legTrace.bits.converged := core.io.commit.bits.converged

  io.in.ready := state === sIdle && core.io.load.ready
  io.out.valid := state === sOutput
  io.out.bits := outcome

  when(io.in.fire) {
    leg := 0.U
    localIteration := 0.U
    totalIterations := 0.U
    solutions := 0.U
    haveBest := false.B
    state := sRun
  }.elsewhen(state === sRun && core.io.commit.valid) {
    localIteration := completedLocal
    totalIterations := completedTotal

    when(candidateWins) {
      haveBest := true.B
      bestScore := candidateScore
      bestCorrection := core.io.commit.bits.decision
    }
    when(core.io.commit.bits.converged) {
      solutions := nextSolutions
    }

    when(legDone) {
      when(advanceLeg) {
        leg := leg + 1.U
        localIteration := 0.U
      }.otherwise {
        outcome.success := nextSolutions.orR
        outcome.correction.zipWithIndex.foreach { case (bit, i) =>
          bit := Mux(
            candidateWins,
            core.io.commit.bits.decision(i),
            Mux(haveBest, bestCorrection(i), core.io.commit.bits.decision(i)),
          )
        }
        outcome.marginal := core.io.commit.bits.marginal
        outcome.residual.zip(core.io.commit.bits.residual).foreach { case (bit, current) =>
          bit := Mux(nextSolutions.orR, false.B, current)
        }
        outcome.totalIterations := completedTotal
        outcome.legsExecuted := leg + 1.U
        outcome.solutionsFound := nextSolutions
        state := sOutput
      }
    }
  }.elsewhen(io.out.fire) {
    state := sIdle
  }
}
